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

## 2026-07-04 Create Request Preflight Guardrail

Goal: continue A1 subscription-era calibration without executing a real generation mutation yet, by making `create-request` dry-run evidence explicit enough to support a later quota-safe mutation.

Start protocol:

- `git fetch origin --prune`: success.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; no tracked changes at start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present locally.
- GitHub plugin PR check failed due to MCP transport to `chatgpt.com/backend-api/ps/mcp`; local `gh` fallback was used.
- `gh pr view 4`: PR #4 open, draft, mergeable, base `main`, head `codex/a1-local-sdk-runner`, head `07d93b3`.
- Recent worklog, command evidence, API calibration docs, field map, and tiny request fixture were read before implementation.
- Peer changes/impact: Explorer-Peer confirmed `origin/dev/g3-a2-calibration` and `origin/codex/a3-p3-ashr-calibration` are older than current A1 subscription work. Their apparent deletion of A1 API/client/dataset surfaces is stale ancestry, not a contract request. Current A1 explicit tool-argument comparison must be preserved because it supports A2/A3 `wrong_arguments` analysis.

Three proposed enhancements:

1. Add strict `create-request` preflight/guardrails and dry-run evidence before real mutation.
2. Execute one real tiny `create-request` after preflight, current usage review, and drift review.
3. Build a public-safe redacted hosted run fixture for A3 from private `create-run` evidence.

Implemented highest ROI enhancement: `create-request` preflight/guardrails only. No real `create-request` was executed.

Subagent findings:

- Bus-Auditor: FAIL for immediate real `create-request`; PASS for dry-run/preflight baseline. Highest ROI is create-request guardrails first, then real mutation after branch drift, tests, and usage review are satisfied.
- Explorer-Peer: keep current A1 API client, dataset-source adapter, explicit wrong-argument grading, and A2 projection helper. Do not adopt stale rollback behavior from peer branches.

Chrome/Product calibration:

- Existing Chrome tab confirmed logged-in `Ashr Labs` at `https://lab.ashr.io/?tab=analysis`, with `Datasets`, `Runs`, `Usage`, `Docs`, and `New dataset`; no sign-in text.
- Usage tab reached `https://lab.ashr.io/?tab=usage` and showed `Usage`, `Monitor your resource consumption`, `Upgrade`, and `Loading usage...`; no visible quota or credits counters loaded.
- Screenshots stored under ignored private evidence: `ashr_lab_analysis_request_round_2026-07-04.png` and `ashr_lab_usage_request_round_2026-07-04.png`.

Implemented:

- `packages/sdk/ashr_clone/api_client.py`: added local-only `preflight` support to call plans and call records. The preflight summary is written to evidence records but is not sent to the Ashr API request body.
- `services/runner/api_probe.py`: added `summarize_generation_request(...)`, `enforce_create_request_preflight(...)`, `--allow-media-generation`, `--allow-non-text-inputs`, and `--max-request-variations`. Real `create-request` execution now blocks unknown variation counts, media generation, non-text inputs, and known variation counts above the configured limit unless explicitly allowed.
- `tests/a1/test_api_client.py`: added coverage for preflight recording, CLI dry-run preflight output, media generation blocking, unknown variation blocking, non-text input blocking, and variation count blocking.
- `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/evidence/commands.md`, `docs/a1/sdk_field_map.md`, and this worklog were updated with non-sensitive evidence.

Verification:

- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `22 passed in 0.77s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `70 passed in 2.62s`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_dry_run.json`: planned create-request, `status=planned`, `attempts=0`.
- Safe dry-run preflight summary: `mutates=true`, `estimated_calls=2`, `num_variations=1`, `num_variations_known=true`, `small_batch=true`, accepted input text only, `non_text_inputs_enabled=false`, and all media/simulation generation flags false.

Remaining:

- Real `create-request` remains blocked until current branch drift, fresh tests, and current usage/plan wording are reviewed again.
- A3 may still want a public-safe redacted hosted run fixture derived from private `create-run` evidence.
- Process-level timeout isolation and TypeScript runtime parity remain future work.

## 2026-07-04 Dataset Source Adapter Round

Goal: finish the next A1 subscription-era adapter step by mapping real Ashr `dataset_source.runs` into existing local runner cases and strict A3 replay fixtures, while keeping raw API evidence private.

Start protocol:

- `git fetch origin`: success; new peer branch observed: `origin/codex/a3-p3-ashr-calibration`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking origin; dirty files were the in-progress A1 dataset adapter, export, CLI, and tests; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` remained untracked/ignored.
- PR check: draft PR #4 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks, head `f508399`.
- Recent worklog and command evidence were read before implementation.
- Peer changes/impact: A3 P3 branch adds calibration mapping docs/tests and redacted fixtures. A1 kept the dataset-source bridge on existing A1 case and run-fixture helpers, so no Gate or dashboard semantics changed.
- Secret handling: no key was printed or committed. The API key remains in ignored `.secrets/ashr.env`; real converted cases and mock run outputs are in ignored `docs/evidence/private_refs/`.

Three proposed enhancements:

1. Land the dataset-source adapter with A3 replay fixture generation using `TraceRecorder` and `build_run_fixture(...)`.
2. Run a mutating `create-run` against an existing dataset after reviewing a dry-run plan and passing `--allow-mutate`.
3. Add process-level isolation for arbitrary external agents if timeout cancellation becomes required.

Implemented highest ROI enhancement: dataset-source adapter and replay fixture generation. Mutating hosted calls remain deferred.

Subagent findings:

- Bus-Auditor before this round: FAIL for PR-ready handoff only because adapter work was dirty/untracked; highest ROI was to land the adapter patch and update non-sensitive docs.
- Explorer-API: confirmed real `dataset_source` shape and edge cases: `runs` is a map, `actions` include 3 agent-side actions in the private sample, `expected_response.tool_calls` may be object-shaped, tag fields vary between null/object/list, and API-level errors can be HTTP 200 with body `status:error`.
- Worker-Replay: recommended explicit dataset-source helper names, summary-only metadata, `requires_external_judge` for empty expected output, and strict replay fixtures via trace helpers instead of hand-written VM frames. These were implemented.

Implemented:

- `packages/sdk/ashr_clone/dataset_adapter.py`: added `DATASET_SOURCE_ADAPTER_VERSION`, `cases_from_dataset_source(...)`, `case_from_source_run(...)`, and `replay_fixture_from_source_run(...)`; normalized object/list tool calls; marked empty expected output with `requires_external_judge`; kept metadata summary-only with hashed source run references.
- `packages/sdk/ashr_clone/__init__.py`: exported dataset-source adapter helpers.
- `services/runner/dataset_adapter.py`: CLI converts API probe records or dataset/source JSON into A1 local cases.
- `tests/a1/test_dataset_adapter.py`: covers source-to-case mapping, single source run selection, empty expected behavior, local runner trace completeness, strict replay fixture validation, and CLI output.
- `services/runner/runner.py` and `tests/a1/test_runner.py`: reviewer follow-up changed tool-call grading to compare arguments when expected calls explicitly include arguments, while preserving name-only compatibility.
- `packages/sdk/ashr_clone/dataset_adapter.py` and `tests/a1/test_dataset_adapter.py`: reviewer follow-up changed `max_cases=0` to emit zero cases and negative `max_cases` to reject.
- `docs/a1/api_calibration/README.md`, `docs/a1/README.md`, `docs/a1/evidence/commands.md`, `docs/a1/sdk_field_map.md`, and this worklog were updated with non-sensitive evidence and next candidates.

Verification:

- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_dataset_adapter.py -q -p no:cacheprovider`: `26 passed in 1.57s`.
- `python -B -m pytest tests/a1/test_dataset_adapter.py -q -p no:cacheprovider`: `6 passed in 0.33s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `62 passed in 2.70s`.
- Private real conversion: `a1_api_get_dataset_first_real.json` converted into 3 local cases under ignored private evidence.
- Private strict replay check: first real source run produced 11 trace events and 11 VM frames; `validate_run_fixture(...)` passed and generated VM stream matched events.
- Private mock run: 3 converted cases ran through `RespondingMockAgent` with `0 errors`, `0 timeouts`, and trace completeness `100.00%`; 3 content failures are expected for the mock agent.
- Chrome read-only check confirmed `https://lab.ashr.io/?tab=analysis` as an Ashr Labs shell with `Datasets` and `Runs` visible and no sign-in text; no key or form input was used.

Remaining:

- Mutating `create-run` and `create-request` are still gated behind dry-run review plus `--execute --allow-mutate`.
- A3 should review the dataset-source replay fixture helper against P3 mapper expectations.
- Stronger timeout isolation and TypeScript parity remain future work.

## 2026-07-04 Create Run Calibration Round

Goal: perform the next highest-ROI subscription-era A1 calibration by uploading one small local run result with `create-run`, then calibrating `get-run`/`poll-run` behavior against the created hosted run.

Start protocol:

- `git fetch origin`: success; new peer branch observed: `origin/dev/g3-a2-calibration`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking origin; no tracked changes at start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present locally.
- PR check: draft PR #4 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks, head `de9d9f5`.
- Recent worklog and A1 command evidence were read before implementation.
- Peer changes/impact: A2 G3 adds `wrong_arguments` evidence, which supports the prior A1 tool-argument comparison fix. A3 P3 remains a report mapper branch; no A1 Gate/dashboard semantics changed.
- Secret handling: key loaded only through ignored `.secrets/load-ashr-env.ps1`; no key, real ids, or raw responses were written to committed docs.

Three proposed enhancements:

1. Run one real `create-run` against an existing private dataset after dry-run review, using `--allow-mutate` and `--max-retries 0`.
2. Exercise `create-request` generation with the tiny request config after quota/plan wording is clearer.
3. Add process-level isolation for arbitrary external agents if hard cancellation becomes required.

Implemented highest ROI enhancement: one real `create-run`, followed by `get-run` and fixed `poll-run` calibration. No `create-request` was executed.

Subagent findings:

- Bus-Auditor: PASS conditional on using the real numeric private dataset id, private result file, explicit output paths under private refs, `--execute --allow-mutate --max-retries 0`, and only public-safe summaries. Main agent followed those constraints.
- Chrome/Product: Ashr Labs remained logged in at `https://lab.ashr.io/?tab=analysis` with `Datasets` and `Runs` visible, no sign-in text, and no visible usage/quota text. Public homepage/docs remained reachable with Docs/Plans/Python SDK/TypeScript/API links and `AshrLabsClient`, `EvalRunner`, `run_and_deploy`/deploy hints.

Implemented:

- `packages/sdk/ashr_clone/api_client.py`: fixed `poll_run` completion to accept observed hosted run-result shapes, not only `aggregate_metrics.tests_passed`.
- `services/runner/api_probe.py`: catches `TimeoutError` and emits a clean `api probe error` instead of a traceback.
- `tests/a1/test_api_client.py`: added real-run-shape poll completion and CLI timeout reporting regressions.
- `docs/a1/api_calibration/README.md`, `docs/a1/README.md`, `docs/a1/evidence/commands.md`, and this worklog: recorded non-sensitive create-run/get-run/poll-run evidence and updated next candidates.

Verification:

- Dry-run create-run: `status=planned`, `attempts=0`, `mutates=true`, `estimated_calls=2`, 3-case private result input.
- Real create-run: `status=ok`, HTTP `200`, `attempts=1`, response keys `_user`, `run`, `status`.
- Created hosted run keys: `created_at`, `dataset`, `id`, `result`, `runner`, `tenant`.
- Created hosted result keys: `aggregate_metrics`, `cases`, `dataset_id`, `duration_ms`, `ended_at`, `errored`, `failed`, `field_map_version`, `max_workers`, `metadata`, `passed`, `run_id`, `runner_id`, `started_at`, `status`, `timed_out`, `total_cases`, `trace_completeness`.
- Real get-run against the created run: `status=ok`, HTTP `200`, `attempts=1`.
- First short poll-run before the fix: record wrote `status=timeout`, HTTP `200`, `attempts=4`, while response already contained `run.result`; CLI traceback exposed a catch gap.
- Fixed real poll-run against the same created run: `status=ok`, HTTP `200`, `attempts=1`.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `16 passed in 0.68s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `64 passed in 2.41s`.

Remaining:

- `create-request` generation remains dry-run only.
- A3 should decide whether it wants a public-safe redacted fixture derived from private hosted run evidence.
- Stronger timeout isolation and TypeScript parity remain future work.

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

## 2026-07-04 Latest Round Index

Latest completed A1 round: Create Request Preflight Guardrail. Full round entry appears above in this worklog under `## 2026-07-04 Create Request Preflight Guardrail`.

Key current facts:

- Current branch remains `codex/a1-local-sdk-runner`; no new branch was created.
- GitHub plugin PR check failed due MCP transport, so `gh` fallback confirmed PR #4 is open, draft, mergeable, and at head `07d93b3` before this local patch.
- Chrome confirmed logged-in Ashr Lab analysis page and a Usage page that showed `Loading usage...` but no visible quota counters.
- Implemented local-only create-request preflight records plus CLI guardrails for media generation and variation count.
- Verification: `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider` -> `22 passed`; `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `70 passed`.
- Tiny `create-request` dry-run was regenerated with `num_variations=1`, text-only accepted input, `non_text_inputs_enabled=false`, all media/simulation generation flags false, `mutates=true`, and `estimated_calls=2`.
- No real `create-request` was executed.

## 2026-07-04 Latest Round Index

Latest active A1 round: Create Request Schema And Media Interface Calibration.

Key current facts:

- Branch remains `codex/a1-local-sdk-runner`; PR #4 was open/draft/mergeable at head `f8e0f8b` at round start.
- `origin/dev/g3-a2-calibration` advanced to `815eb31`; its A1-file deletions are stale ancestry, not an A1 rollback signal.
- Chrome/public docs check: official docs live at `https://ashr.io/docs/python-sdk/overview/`; `/docs` returned 404. API reference lists `create_request` and says `request_input_schema` is optional with a permissive default.
- Chrome Usage page intermittently showed visible Image/Audio/Files usage counters, but direct reload sometimes showed only `Loading usage...`.
- First real text-only `create-request` attempt after dry-run returned API-level error: HTTP `200`, `attempts=1`, `request_input_schema is required`.
- Implemented SDK parity: `AshrApiClient.create_request(...)` now sends a permissive default `request_input_schema` when omitted; agent tools are included under `tools`.
- Added dry-run-only Image/Audio/Files media interface fixture at `docs/a1/api_calibration/media_interface_request.json`.
- Verification: `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider` -> `25 passed`; `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `73 passed`.
- Dry-run evidence: text-only tiny request now records `request_input_schema_source=client_default` and schema keys `additionalProperties`, `tools`, `type`; media-interface dry-run records `generate_images=true`, `generate_audio=true`, `media_generation_enabled=true`, and `non_text_inputs_enabled=true`.
- No successful real `create-request` has completed yet. Next step is to commit the schema/media coverage patch, then retry exactly one text-only schema-backed real `create-request` from a clean branch with `--max-retries 0`.

## 2026-07-04 Real Request And Media Boundary Calibration

Goal: continue A1 subscription-era SDK/Runner calibration by running the schema-backed real `create-request`, expanding Image/Audio/Files interface coverage, using paid API calls more actively within dry-run-first controls, and hardening runner guardrails before additional real generation.

Start protocol:

- `git fetch origin`: success; `origin/dev/g3-a2-calibration` advanced from `815eb31` to `ab51ced`, then `git fetch --all --prune` advanced it again to `eec51c6`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracked `origin/codex/a1-local-sdk-runner`; tracked worktree was clean at the start. Ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` were present.
- `gh pr view 4 --repo 3351666087/ashr-codex-factory --json number,state,isDraft,mergeable,headRefName,headRefOid,url`: PR #4 open/draft at head `7b15ad5`.
- `gh pr list --repo 3351666087/ashr-codex-factory --state all --limit 30 --json ...`: open PRs were A1 PR #4 and A3 PR #5; PRs #1/#2/#3 were merged history.
- Peer changes/impact: A2/G3 and A3/P3 branches are additive in A2/A3/judge/report areas. Their stale-ancestry diffs still show A1 API file deletion relative to this branch; this remains a branch ancestry artifact, not an A1 rollback signal.

Three proposed enhancements:

1. Harden real mutating API guardrails before more paid generation: force `--max-retries 0`, stricter `num_variations`, official `{enabled: bool}` accepted-input parsing, unsupported-shape blocking, and safer evidence params.
2. Add canonical `AgentInput` multimodal envelope in `AgentAdapter` and expand default request schema to advertise `parts`.
3. Add larger real generation batches and media-generation calibration.

Implemented highest ROI enhancement: guardrail and evidence hardening, plus concrete Image/Audio/Files dry-run fixture coverage. After the guardrail patch passed tests, the main agent also ran one real text-only success chain, one real media-boundary chain, and one attempted text batch that exposed hosted request quota exhaustion.

Subagent findings:

- Bus-Auditor: PASS for exactly one text-only schema-backed real request with explicit private output, `--execute --allow-mutate --max-retries 0`, and public-safe summaries. Warned not to execute the media fixture without a fresh usage review.
- Worker-Adapter: flagged future multimodal input gaps in `AgentAdapter`, including lack of a canonical `AgentInput` envelope and content-part text normalization. Deferred to the next round because runner guardrails were the immediate prerequisite for more real API use.
- Explorer-SDK: flagged missing positive Files coverage, direct-client guardrail docs, explicit schema passthrough tests, and non-exhaustive media/non-text guardrail tests. Files fixture and tests were implemented; direct-client thin/unguarded posture remains a docs/future-SDK decision.
- Explorer-Chrome/Product: confirmed official Python API reference fields for `create_request`, `accepted_inputs` keys, media generation flags, request object fields, and builder file APIs. Lab Usage showed Image/Audio/Files used-of-limit counters; exact private values remain private evidence.
- Worker-Runner: flagged P1 duplicate-generation risk because CLI default retries were still allowed for real `create-request`, plus permissive variation coercion and unsupported `accepted_inputs` shapes. All were fixed and tested.

Implemented:

- `services/runner/api_probe.py`: real mutating API calls now refuse nonzero `--max-retries` before env/key resolution; `num_variations` accepts only positive ints or digit-only positive strings; `accepted_inputs` supports booleans and `{enabled: bool}`; unsupported accepted-input shapes are blocked before mutation.
- `packages/sdk/ashr_clone/api_client.py`: direct SDK `create_run(..., dry_run=False)` and `create_request(..., dry_run=False)` now require `max_retries=0` to avoid duplicate mutation on retry.
- `packages/sdk/ashr_clone/api_client.py`: `call(...)` accepts `record_params`; `create_request(...)` still sends the full API body but records a summary-shaped request/schema params object to reduce raw prompt/context exposure in evidence records.
- `docs/a1/api_calibration/media_interface_request.json`: expanded from Image/Audio to Image/Audio/Files coverage with `generate_files=true` and accepted `file=true`.
- `docs/a1/api_calibration/text_batch_generation_request.json`: added a 3-variation text-only paid API calibration fixture.
- `tests/a1/test_api_client.py`: added coverage for explicit request schema passthrough, request evidence shape summaries, schema-file source labeling, strict variation parsing, `{enabled: bool}` accepted inputs, unsupported accepted-input blocking, exhaustive non-text input/media generation flags, zero-retry enforcement before env lookup, and execute-path guardrail blocking before client calls.
- `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/evidence/commands.md`, and this worklog were updated with public-safe evidence.

Verification and real API evidence:

- Chrome Usage check: logged-in Usage page visible; Image/Audio/Files counters and period text were visible; screenshot stored under ignored private evidence.
- Official docs check: Python API reference confirmed `accepted_inputs` keys `text`, `audio`, `file`, `image`, `video`, `conversation`, generation flags `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, `generate_simulations`, and request fields including `request_status`.
- Text-only schema-backed `create-request`: real call succeeded with HTTP `200`, `status=ok`, `attempts=1`, response keys `_user`, `request`, `status`.
- Text-only `get-request`: real read-only follow-up succeeded with HTTP `200`, `status=ok`, `attempts=1`, request status initially `processing`.
- Text-only `poll-request`: real poll succeeded with HTTP `200`, `status=ok`, `attempts=1`, request status `completed`; completed request includes duration/completion fields and `request_input_schema`.
- Image/Audio/Files dry-run: planned record shows media generation `audio/files/images=true`, accepted input flags `audio/file/image/text=true`, `num_variations=1`.
- Image/Audio/Files real request: `create-request` was accepted with HTTP `200`, `status=ok`, `attempts=1`; follow-up `get-request` returned hosted `request_status=failed` with completion/duration fields present. `poll-request` recorded a public-safe error summary, HTTP `200`, `attempts=1`, message `request failed`.
- Text-only 3-variation batch dry-run passed local preflight, but real execution returned hosted API-level usage error: request quota exhausted for the current period. No retry was attempted.
- Read-only `list-requests --limit 5` after the real probes succeeded with HTTP `200`, `status=ok`, `attempts=1`; public-safe aggregate: 5 requests, status distribution `completed=3`, `failed=2`.
- Read-only `list-datasets --limit 5` succeeded with HTTP `200`, `status=ok`, `attempts=1`; public-safe aggregate: 3 datasets.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `37 passed in 1.22s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `85 passed in 3.13s`.

Remaining:

- Hosted media-generation failure reason is not visible in the public-safe request fields observed so far; do not repeat the same media request blindly. Next media step should adjust schema/request shape or inspect official product docs/UI for required media payload semantics.
- Request generation quota is currently exhausted for additional `create-request` calls in this period/account state; continue with read/list/get/poll calibration, existing completed datasets, runner replay, and docs until quota resets or plan changes.
- Adapter still lacks the proposed canonical multimodal `AgentInput` envelope and content-part text normalization; this is the next highest ROI implementation once mutation guardrails are stable.

## 2026-07-04 AgentInput Multimodal Envelope

Goal: implement the next highest-ROI A1 local SDK/Adapter step after real request guardrails by adding a canonical multimodal `AgentInput` envelope for Image/Audio/Files interfaces, while preserving legacy text-only adapter behavior and A2/A3 `AgentTurn` output contracts.

Start protocol:

- `git fetch --all --prune`: success; `origin/dev/g3-a2-calibration` advanced to `c2d1561`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking origin; tracked changes at start were the in-progress A1 adapter draft only. Ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` were present and unstaged.
- `gh pr list --repo 3351666087/ashr-codex-factory --state all --limit 30 --json ...`: open PRs remained A1 PR #4 and A3 PR #5; PRs #1/#2/#3 were merged history.
- Peer changes/impact: A2/G3 continued additive A2 calibration work and A3 PR #5 stayed in A3 dashboard/report scope. No live peer change required modifying A1 `AgentTurn`, A2 projection, judge semantics, or dashboard behavior.

Three proposed enhancements:

1. Add canonical `AgentInput` multimodal envelope plus adapter methods and content-part output normalization.
2. Adjust the hosted media request schema/UI calibration before repeating Image/Audio/Files generation.
3. Add a second external-agent adapter smoke path against the new envelope.

Implemented highest ROI enhancement: `AgentInput` and adapter input/output boundary coverage.

Subagent findings:

- Bus-Auditor: PASS to proceed with local `AgentInput`; BLOCK any new real `create-request` because hosted request quota was exhausted in the latest evidence. Main agent performed no new real generation request calls.
- Explorer-SDK: recommended `AgentInput` next to `AgentResult`, schema `ashr.clone.agent_input.v1`, parts for `text`, `image`, `audio`, and `file`, explicit `respond_input`/`arespond_input`, top-level exports, schema snapshot, and docs.
- Reviewer: requested content-part output normalization and adapter error redaction for local failures that may include file paths, signed URLs, tokens, or owner emails.

Implemented:

- `packages/sdk/ashr_clone/adapter.py`: added `AgentInput`, `AGENT_INPUT_SCHEMA_VERSION`, `coerce_agent_input`, multimodal part normalization, explicit `respond_input`, `arespond_input`, `run_input_turn`, and `arun_input_turn`. Legacy `respond("text")` still passes a plain string by default.
- `packages/sdk/ashr_clone/adapter.py`: content-part outputs now extract text from `text`, `input_text`, and `output_text` parts instead of JSON-dumping the entire multimodal list.
- `packages/sdk/ashr_clone/adapter.py`: adapter error payloads and captured kwargs redact token-like values, bearer tokens, emails, and signed URL query strings.
- `packages/sdk/ashr_clone/__init__.py`: exported `AgentInput`, `AGENT_INPUT_SCHEMA_VERSION`, and `coerce_agent_input`.
- `docs/a1/schemas/agent_input.schema.json`: added the A1 AgentInput schema snapshot for A3/Gate review.
- `tests/a1/test_adapter.py`: added coverage for text default compatibility, envelope passing, keyword style, image/audio/file parts, async envelope use, content-part text extraction, A2 projection stability, and redacted error payloads.
- `tests/a1/test_trace_fixture.py`: added schema snapshot coverage for `agent_input.schema.json`.
- `docs/a1/README.md`, `docs/a1/explorer_sdk.md`, `docs/a1/sdk_field_map.md`, `docs/a1/api_calibration/README.md`, `docs/a1/evidence/commands.md`, and this worklog were updated with public-safe summaries.

Verification:

- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `21 passed in 0.10s`.
- `python -B -m pytest tests/a1/test_trace_fixture.py -q -p no:cacheprovider`: `8 passed in 0.27s`.
- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_api_client.py -q -p no:cacheprovider`: `56 passed in 2.64s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `92 passed in 2.96s`.
- Chrome read-only calibration: logged-in Usage page showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` with no sign-in copy; exact private usage values were not recorded in tracked docs. Official API reference remained reachable and showed `create_request`, `accepted_inputs`, `generate_audio`, `generate_files`, `generate_images`, and `add_user_file`.
- Final remote recheck before staging: `git fetch --all --prune` advanced `origin/main` to `2205084` and `origin/dev/g3-a2-calibration` to `3c27179`; PR #4 and PR #5 are now merged. `origin/main` contains A1 plus additive A2/A3/judge/dashboard/report fixture work. Current A1 patch remains a follow-up on `codex/a1-local-sdk-runner`.
- Bus-Auditor final verdict: PASS. No must-fix items; safe to stage/commit self-made A1 SDK/tests/docs plus this shared worklog. It noted that pushing the branch is safe but will not update a merged PR, so a fresh PR or handoff is needed after push if collaboration visibility is required.
- Commit/push/PR: pushed `2624ea6` to `codex/a1-local-sdk-runner` and opened draft PR #6, `A1 AgentInput multimodal adapter envelope`, because earlier PR #4 had already merged.

Remaining:

- Need inspect/adjust hosted media request schema/UI before any further Image/Audio/Files generation. Keep `create-request` blocked until quota resets or plan state changes.
- Hosted media-generation failure reason is still unresolved; do not repeat the same media request blindly. Next media step should adjust schema/request shape or inspect official product docs/UI for required media payload semantics.
- Request generation quota remains treated as exhausted for new `create-request` calls until quota resets or plan state changes; read/list/get/poll calibration remains allowed.
- A second external-agent adapter smoke path against `AgentInput` would be useful once the local envelope is committed.

## 2026-07-04 Media Request Input Schema Calibration

Goal: continue A1 subscription-era SDK/Runner calibration by making the dry-run/default `request_input_schema` for Image/Audio/Files align with the local `AgentInput` multimodal envelope before any further hosted media generation.

Start protocol:

- `git fetch --all --prune`: success; `origin/dev/g3-a2-calibration` advanced to `145f6ad`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present.
- `gh pr list --repo 3351666087/ashr-codex-factory --state all --limit 30 --json ...`: PR #6 open/draft at head `0870fc8`; PR #4 and PR #5 merged.
- Peer changes/impact: A2/G3 new commit touched A2 docs/fixtures/judge/report/tests only. No A1-owned file changes or A1 rollback signal were observed.

Three proposed enhancements:

1. Add `AgentInput` media part shape to default `request_input_schema` and dry-run evidence.
2. Inspect hosted media failure details or UI-required payload semantics before repeating media generation.
3. Add a second external-agent adapter smoke path against the `AgentInput` envelope.

Implemented highest ROI enhancement: default media request schema and dry-run evidence shape.

Subagent findings:

- Bus-Auditor start audit: PASS. Main agent should keep `create-request` mutation blocked while quota state is exhausted/unclear, and should make a local schema/dry-run improvement first.
- Chrome/Product read-only check: official API reference showed `request_input_schema`, `accepted_inputs`, media generation flags, and `TestBuilder.add_user_file(file_path, description, action_index)`. Lab Usage was logged in but only stably showed `Usage`, `Upgrade`, and `Loading usage`; exact private usage values were not recorded in tracked docs.

Implemented:

- `packages/sdk/ashr_clone/api_client.py`: `build_default_request_input_schema(...)` now keeps `additionalProperties=true` and adds optional `schema_version`, `text`, `parts`, `metadata`, and `$defs.agent_input_part` when accepted inputs include `image`, `audio`, or `file`; part types match enabled accepted inputs.
- `packages/sdk/ashr_clone/api_client.py`: create-request evidence summaries now include `property_keys`, `defs_keys`, `agent_input_schema_version`, and `agent_input_part_types` for the request input schema.
- `services/runner/api_probe.py`: create-request preflight now records `agent_input_part_types` and `agent_input_schema_version` for non-text media inputs.
- `tests/a1/test_api_client.py`: added coverage for media-aware default schema and media fixture dry-run record shape.
- `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/evidence/commands.md`, and this worklog were updated with public-safe summaries.

Verification:

- `python -B -m services.runner.api_probe create-request --request-name "A1 Media Interface Schema Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_api_media_interface_schema_dry_run.json`: `status=planned`, `attempts=0`.
- Safe dry-run summary: `agent_input_schema_version=ashr.clone.agent_input.v1`, schema property keys `metadata`, `parts`, `schema_version`, `text`, schema defs `agent_input_part`, schema part types `audio`, `file`, `image`, `text`, preflight part types `text`, `image`, `audio`, `file`, media generation enabled, and non-text inputs enabled.
- Chrome screenshot stored under ignored private evidence: `docs/evidence/private_refs/ashr_lab_usage_media_schema_round_2026-07-04.png`.
- Bus-Auditor must-fix: direct `enum` schemas for non-text-only inputs were not reflected in schema summaries. Fixed `_schema_agent_input_part_types(...)` and added a dry-run record summary regression for image-only accepted input.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `41 passed in 1.16s`.
- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `21 passed in 0.09s`.
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_adapter.py -q -p no:cacheprovider`: `62 passed in 1.15s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `96 passed in 2.92s`.
- `git diff --check`: clean except CRLF warnings.

Remaining:

- Need final Bus-Auditor recheck after diff/check/secret scan.
- Hosted media-generation failure reason remains unresolved; next step should inspect hosted failure/UI payload semantics or use read-only request details before repeating media generation.
- Request generation quota remains treated as exhausted for new `create-request` calls until quota resets or plan state changes; read/list/get/poll calibration remains allowed.
- A second external-agent adapter smoke path against `AgentInput` is still useful.

## 2026-07-04 Latest Round Index

Latest active A1 round: Media Request Input Schema Calibration.

Key current facts:

- Branch remains `codex/a1-local-sdk-runner`; PR #6 is open/draft and will receive this follow-up if committed.
- `AgentInput` local envelope exists with `schema_version=ashr.clone.agent_input.v1` and supports `text`, `image`, `audio`, and `file` parts.
- Default `create-request` schema now advertises `AgentInput` `parts` for Image/Audio/Files accepted inputs while staying permissive with `additionalProperties=true`.
- A2/A3-facing `AgentTurn` output shape remains intact, with content-part text extraction and A2 projection tests passing.
- Additional real text batch generation is blocked by hosted request quota exhaustion. Read-only API probes still work.
- A1 tests are now `96 passed`.

## 2026-07-04 Hosted Media Failure Detail Calibration

Goal: continue A1 subscription-era SDK/Runner calibration by inspecting the previously accepted-but-failed hosted Image/Audio/Files request through read-only evidence, then making `get-request` and `poll-request` records preserve safe failure details for A2/A3-facing debugging without exposing raw private values.

Start protocol:

- `git fetch origin --prune`: success.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; tracked worktree clean at start. Ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` were present and unstaged.
- `gh pr view 6 --repo 3351666087/ashr-codex-factory --json number,state,isDraft,mergeable,headRefName,headRefOid,url`: PR #6 open/draft/mergeable at head `87fd28c`.
- Peer changes/impact: latest `origin/dev/g3-a2-calibration` commit `96ff7d5` touched A2 scenario/judge/report evidence files. No live peer change required modifying A1 contracts, judge semantics, or dashboard business logic.

Three proposed enhancements:

1. Add hosted request failure-shape summaries to `get-request` / `poll-request` records.
2. Re-run media generation with a revised schema and real paid API call.
3. Add the second external-agent adapter smoke path against `AgentInput`.

Implemented highest ROI enhancement: hosted request failure-shape summaries. This was chosen because it extracts value from existing paid API evidence and reduces future debugging risk before spending another media-generation request.

Evidence and implementation:

- Existing read-only recheck `docs/evidence/private_refs/a1_api_media_interface_get_request_recheck_real.json` showed `status=ok`, HTTP `200`, `attempts=1`, hosted `request_status=failed`.
- Safe failure shape: no top-level failure-like hosted request keys; nested `request.request` keys included `_failure`, `agent`, `context`, `generation_options`, `metadata`, and `test_config`; `_failure` was an object with keys `at` and `error`, both strings. Raw values remain in ignored private evidence only.
- `packages/sdk/ashr_clone/api_client.py`: added `summarize_request_failure(...)` and response summary attachment so failed `get-request` records include `response_summary.request_failure`, and failed `poll-request` error records include `error.failure_summary`.
- `tests/a1/test_api_client.py`: added failed `get-request` and failed `poll-request` regressions, including token/email redaction and a completed-request false-positive guard for ordinary `requestor_details` fields.
- `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/evidence/commands.md`, and this worklog were updated with public-safe summaries.

Verification so far:

- `python -B -c "... summarize_request_failure(...)"`: helper emitted only keys, types, string lengths, and nested request keys for the private failed media request.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `44 passed in 1.18s`.
- Chrome read-only calibration: official API reference showed `create_request`, `request_input_schema`, `accepted_inputs`, `generate_audio`, `generate_images`, and `add_user_file`. Existing logged-in Usage tab showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without sign-in copy; exact usage counters remain private and screenshots are stored under ignored `docs/evidence/private_refs/`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `99 passed in 2.94s`.
- `git diff --check`: exit 0; CRLF warnings only.
- Added-line sensitive scan: implementation/docs matched no real key, request id, email, or exact usage patterns. Test-only matches were synthetic redaction fixtures.

Remaining:

- Run final Bus-Auditor recheck.
- Do not repeat media generation until UI-required payload semantics or quota state are clearer; read/list/get/poll calibration remains allowed.

## 2026-07-04 Read-Only API Parity Surface

Goal: close a read-only API surface gap exposed by A2's new real API smoke evidence by adding official SDK parity for `health_check()` and `list_agents()` to the A1 clone SDK/Runner probe.

Start protocol:

- `git fetch origin --prune`: success; `origin/dev/g3-a2-calibration` advanced to `561aa0e`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; tracked worktree clean at start. Ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` were present and unstaged.
- `gh pr view 6 --repo 3351666087/ashr-codex-factory --json number,state,isDraft,mergeable,headRefName,headRefOid,url`: PR #6 open/draft/mergeable at head `05b4b44`.
- Peer changes/impact: A2/G3 commit `561aa0e` added a redacted real API smoke summary and media calibration fixture on the A2 branch. It did not touch A1-owned files, but it showed A1 lacked `health-check` and `list-agents` parity.

Three proposed enhancements:

1. Add read-only `health-check` / `list-agents` SDK and CLI parity, then run real read-only probes.
2. Revisit media generation semantics and attempt another paid media `create-request`.
3. Add a second external-agent adapter smoke path against `AgentInput`.

Implemented highest ROI enhancement: read-only API parity. This improves real-Ashr alignment and core command coverage without spending generation quota.

Evidence and implementation:

- Local official wheel inspection confirmed `AshrLabsClient.health_check()` sends API function `keep_alive`; `AshrLabsClient.list_agents()` sends `list_agents` and returns an `agents` list.
- `packages/sdk/ashr_clone/api_client.py`: added `health_check(...)` and `list_agents(...)`.
- `services/runner/api_probe.py`: added CLI operations `health-check` and `list-agents`.
- `tests/a1/test_api_client.py`: added SDK and CLI dry-run/execute coverage for both operations.
- Dry-run evidence written to ignored `docs/evidence/private_refs/a1_api_health_check_dry_run.json` and `docs/evidence/private_refs/a1_api_list_agents_dry_run.json`.
- Real read-only evidence written to ignored `docs/evidence/private_refs/a1_api_health_check_real.json` and `docs/evidence/private_refs/a1_api_list_agents_real.json`.
- Safe real summary: `health-check` returned HTTP `200`, `status=ok`, `attempts=1`, function `keep_alive`, response keys `db`, `message`, `status`; `list-agents` returned HTTP `200`, `status=ok`, `attempts=1`, function `list_agents`, response keys `_user`, `agents`, `status`, and `agents_count=0`.
- Chrome read-only calibration: official API reference showed `health_check`, `list_agents`, `list_datasets`, `list_requests`, and `create_request`; existing logged-in Usage tab showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without sign-in copy. Exact counters remain private and screenshots stay under ignored `docs/evidence/private_refs/`.

Verification so far:

- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `47 passed in 1.57s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `102 passed in 3.27s`.
- `git diff --check`: exit 0; CRLF warnings only.
- Added-line value-oriented sensitive scan: no token-like key value, bearer token, email, private request id, or exact usage pattern. A broader scan matched only the public env var name `ASHR_LABS_API_KEY` in the field map.

Remaining:

- Run final Bus-Auditor recheck.
- No `create-request` or `create-run` was executed in this round.

## 2026-07-04 Local Cloud API Runtime Skeleton

Goal: begin the long-running A1 cloud-runtime phase by adding the smallest local-only API service skeleton that can hold tenant/project/dataset/request/run state, submit existing A1 `RunResult` payloads, poll stored run status, export run fixtures for A3, and enforce a project-scoped quota ledger without calling hosted Ashr APIs.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced to `ddd615a`.
- `gh pr list --state all`: PR #6 `A1 AgentInput multimodal adapter envelope` open/draft on `codex/a1-local-sdk-runner`; earlier A1/A2/A3 PRs are merged history.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present and unstaged.

Baseline scan:

- Existing A1 Python surfaces: `packages/sdk/ashr_clone/{api_client.py,adapter.py,trace.py,dataset_adapter.py,types.py}`, `services/runner/{api_probe.py,cli.py,runner.py,dataset_adapter.py}`, `examples/agents/mock_agent.py`, `tests/a1/test_{adapter,api_client,dataset_adapter,runner,trace_fixture}.py`, and A1 docs/schemas/evidence.
- Existing capabilities: local MockAgent + CLI; 30-80 case runs; max workers normalized to at least 4; A3 run fixture/replay; `AgentInput` multimodal envelope; read-only API parity for `health-check` and `list-agents`; guarded mutating `create-run` and `create-request`; private real API evidence under ignored `docs/evidence/private_refs/`.
- Missing before this round: `services/api`, `services/cloud`, `packages/ts`, root `package.json`, root `pyproject.toml`, root `requirements.txt`, tenant/project cloud runtime, local quota ledger, TypeScript SDK package.
- Peer changes/impact: latest A2/G3 commit `ddd615a` touched `docs/a2/scenario_coverage_plan.md`, `fixtures/a2/results/a2_g3_coverage_report.json`, `packages/scenarios/a2_g3_full_pack.json`, `services/judge/coverage.py`, `tests/a2/test_contracts.py`, and `tests/a3/report_builder.test.mjs`. No A1-owned or contract-breaking change observed.

Three proposed enhancements:

1. Local cloud API skeleton with tenant/project/dataset/run/request state and in-memory quota ledger. Scores: demo value 5, risk reduction 4, contract impact 2, estimated effort 3, API evidence value 3.
2. Standalone quota ledger hardening for API probe and runner operations. Scores: demo value 3, risk reduction 4, contract impact 1, estimated effort 2, API evidence value 2.
3. TypeScript SDK quickstart scaffold. Scores: demo value 4, risk reduction 3, contract impact 2, estimated effort 4, API evidence value 2.

Implemented highest ROI enhancement: local cloud API skeleton.

Subagent findings:

- Bus-Auditor: PASS with tight scope. Keep implementation A1-owned/local-only, avoid new undeclared runtime deps, no judge/dashboard/Gate changes, and no real `create-request` / `create-run`.
- Explorer-SDK/API: Python API probe is strong, but no integrated local cloud runtime existed; batch runner remains text-first for media cases; hosted media semantics remain unresolved; quota is guardrail-based; TypeScript parity absent.
- Explorer-Chrome/Product: official API reference showed request/media boundary fields including `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `request_status`, `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, `generate_simulations`, and file-upload style fields. Logged-in Usage showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without recording exact private counters. Screenshot stayed ignored at `docs/evidence/private_refs/ashr_lab_usage_hosted_media_failure_detail_round_2026-07-04.png`.
- Worker-Runtime: independently converged on the same bounded `services/api` shape and verified `tests/a1` at 108 passed before the main agent added one validation/quota transaction regression, bringing the final total to 109 passed.
- Worker-TS/Reviewer: confirmed no TS package exists; recommended future `packages/ts/ashr-clone` with injected `fetch`, dry-run default, env-key parity, and redaction/zero-retry tests.

Implemented:

- `services/api/runtime.py`: added `CloudApiService`, `InMemoryCloudStore`, `QuotaLedger`, `CloudApiError`, `ValidationError`, `NotFoundError`, and `QuotaExceededError`.
- `services/api/runtime.py`: tenant/project isolation; dataset import/list/get; request create/list/get; run submit/list/get/poll; observation append; run fixture export/write; project-scoped quota snapshot.
- `services/api/__init__.py`: exported the local cloud runtime surface.
- `docs/a1/schemas/cloud_api.schema.json`: added schema snapshot for local runtime records.
- `tests/a1/test_cloud_api.py`: added coverage for dataset import, local runner submit, polling, fixture export, tenant/project isolation, media request schema preservation, validation errors that do not consume quota, and quota blocking before writes.
- `tests/a1/test_trace_fixture.py`: added cloud schema version guard.
- `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, `docs/a1/evidence/commands.md`, and this worklog were updated with public-safe summaries.

Verification:

- `python -B -m pytest tests/a1/test_cloud_api.py -q -p no:cacheprovider`: 7 passed.
- `python -B -m pytest tests/a1/test_trace_fixture.py -q -p no:cacheprovider`: 8 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 109 passed.
- Chrome official docs check: API reference reachable and shows request/media boundary fields above.
- Chrome Usage check: logged-in page showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact counters remain private.
- Final remote recheck before staging: `origin/dev/g3-a2-calibration` advanced to `bee20af`, touching A2 docs/evidence/scripts/tests only (`docs/a2/README.md`, `docs/evidence/a2_real_api_smoke.json`, `scripts/a2_regenerate_fixtures.py`, `tests/a2/test_contracts.py`). No A1-owned file impact observed.
- Real API calls: none in this round.

Remaining / next top 3:

1. Add a small local API/CLI demo path that runs an external agent, submits the `RunResult` into `CloudApiService`, polls it, and writes a fixture.
2. Start TypeScript SDK quickstart parity against the new cloud runtime and existing Python API client constants.
3. Investigate hosted media payload semantics/read-only failure details before any repeat Image/Audio/Files generation.

## 2026-07-04 Local Cloud API Demo CLI

Goal: turn the in-memory cloud runtime into a fresh-setup demo path that proves an external agent can be loaded, run through the local runner, submitted to `CloudApiService`, polled, and exported as a fixture without any hosted Ashr API call.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; no A1 branch advancement observed.
- `gh pr list --state all`: PR #6 remains open/draft on `codex/a1-local-sdk-runner`; earlier PRs remain merged history.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present and unstaged.

Baseline scan:

- Existing A1 surfaces: Python SDK/Adapter/Runner/Trace/API probe, `services/api` local runtime skeleton, MockAgent, A1 tests/docs/schemas, ignored private real API evidence.
- Existing cloud runtime: `CloudApiService`, `InMemoryCloudStore`, `QuotaLedger`, tenant/project/dataset/request/run state, run submit/poll/export, schema snapshot, and 109 passing A1 tests.
- Missing before this round: `services/api/cli.py`, `services/api/demo.py`, TypeScript package, package.json, cloud demo fixture command, and end-to-end local API demo docs.
- Peer changes/impact at round start: latest `origin/dev/g3-a2-calibration` commit was `bee20af`, touching A2 docs/evidence/scripts/tests only. No A1-owned file impact observed.

Three proposed enhancements:

1. Local cloud API demo CLI: demo value 5, risk reduction 4, contract impact 2, estimated effort 3, API evidence value 3. Selected because it proves the cloud runtime is usable from fresh setup.
2. TypeScript SDK quickstart scaffold: demo value 4, risk reduction 3, contract impact 2, estimated effort 4, API evidence value 2.
3. Hosted media semantics read-only calibration: demo value 3, risk reduction 4, contract impact 1, estimated effort 3, API evidence value 4.

Implemented highest ROI enhancement: local cloud API demo CLI.

Implemented:

- `services/api/demo.py`: added `run_agent_cloud_demo(...)`, which loads cases, creates local tenant/project/dataset records, runs an external agent target through `run_agent_batch`, submits the result into `CloudApiService`, polls the run, writes an A3-consumable fixture, optionally writes run-result JSON, and emits a safe summary.
- `services/api/cli.py`: added `python -B -m services.api.cli run-agent`, including fixture/summary/run outputs, tenant/project/dataset identifiers, runner config, timeout config, and `--fail-on-case-failure`.
- `services/api/__init__.py`: exported `run_agent_cloud_demo`.
- `packages/sdk/ashr_clone/api_client.py`: redaction now covers `sk-...` style key strings in addition to existing token/Bearer/email patterns.
- `packages/sdk/ashr_clone/adapter.py`: adapter error redaction now covers `sk-...` style key strings too, keeping run-result/fixture output aligned with API-client redaction.
- `services/api/cli.py`: operational errors now pass through SDK `redact_text(...)` before reaching stderr.
- `tests/a1/test_adapter.py`, `tests/a1/test_api_client.py`, `tests/a1/test_cloud_api.py`, `tests/a1/test_cloud_api_cli.py`, and `tests/a1/fixtures_sensitive_agent.py`: added helper, CLI success, CLI failure-return, negative timeout, operational error redaction, fixture/run-output leak checks, adapter redaction, and SDK redaction coverage.
- `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/evidence/commands.md`, `docs/evidence/official_site_gaps.md`, and this worklog were updated.

Verification:

- Local smoke command: `python -B -m services.api.cli run-agent --input docs/a1/evidence/local_agent_cases_30.json --agent examples.agents.mock_agent:RespondingMockAgent --fixture-output docs/evidence/private_refs/a1_cloud_demo_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_cloud_demo_summary_smoke.json --run-output docs/evidence/private_refs/a1_cloud_demo_run_smoke.json --tenant-id tenant_a1_smoke --project-id project_a1_smoke --dataset-id dataset_a1_smoke --max-workers 4 --timeout 5 --fail-on-case-failure`.
- Local smoke result: 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, trace completeness 1.0; quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`. Outputs stayed under ignored private evidence.
- Chrome official docs check: API reference reachable and shows `create_run`, `get_run`, `list_runs`, `poll_run`, dataset/list/get, request fields, health, and agents surfaces.
- Chrome Usage check: logged-in page showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact counters remain private. Screenshot stored at ignored `docs/evidence/private_refs/ashr_lab_usage_cloud_demo_2026-07-04.png`.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 15 passed.
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 62 passed.
- Bus-Auditor final must-fix: adapter redaction did not yet cover `sk-...`, so sensitive agent errors could still enter fixture/run JSON. Fixed adapter redaction and added fixture/run-output leak assertions.
- `python -B -m pytest tests/a1/test_adapter.py tests/a1/test_api_client.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 83 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 117 passed.
- Final remote recheck before staging: `origin/dev/g3-a2-calibration` advanced to `31ff317`, touching A2 docs/worklog/fixtures/scripts plus `services/judge` and `tests/a2` only. No A1-owned file impact observed.
- Final GitHub recheck: PR #6 remained open/draft on `codex/a1-local-sdk-runner`; `HEAD..origin/codex/a1-local-sdk-runner` was empty before staging.
- `git diff --check`: no whitespace errors; Windows line-ending warnings only.
- Sensitive scan over changed A1/docs files: matches were public env var names, redaction constants, private-evidence path references, and synthetic test strings only. No real key, `.secrets/`, or private raw evidence file was staged.
- Final Chrome main-thread recheck: API reference still exposed the run/dataset/request/health/agent fields above. Usage page initially loaded asynchronously, then showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` with no `Login`/`Sign in`; exact private counters were not recorded.
- Final Bus-Auditor: PASS after adapter redaction fix. Required staging note: include the four untracked source/test files with the tracked changes; do not stage `.secrets/`, `.pytest_cache/`, or `docs/evidence/private_refs/`.
- Real API calls: none in this round.

Remaining / next top 3:

1. Start TypeScript SDK quickstart parity against the Python API client and local cloud runtime.
2. Add a queue worker facade around the local cloud runtime so submitted runs can move through queued/running/completed states.
3. Investigate hosted media payload semantics/read-only failure details before any repeat Image/Audio/Files generation.

## 2026-07-04 TypeScript SDK Quickstart Parity

Goal: add the first local-only TypeScript SDK quickstart surface so external TS agents and tools can use A1 `AgentInput`, cloud runtime, quota ledger, redaction, request schema helpers, and fixture export without hosted Ashr API calls.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced from `31ff317` to `a6ee272`.
- `gh pr list --state all`: PR #6 remains open/draft on `codex/a1-local-sdk-runner`; earlier PRs remain merged history.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present and unstaged.

Baseline scan:

- Existing A1 surfaces: Python SDK/Adapter/Runner/Trace/API probe, `AgentInput`, `services/api` local runtime, cloud demo CLI, MockAgent, A1 tests/docs/schemas, ignored private real API evidence.
- Missing before this round: `packages/ts`, package metadata, TypeScript source, TypeScript tests, and TypeScript quickstart docs.
- Peer changes/impact: latest A2/G3 commit `a6ee272` added an Ashr grading import bridge under `docs/a2`, `fixtures/a2`, `scripts/a2_import_ashr_grading.py`, `services/judge`, and `tests/a2`. No direct A1-owned file conflict. It creates an optional future path for A1-hosted run evidence into A2 calibration, but no immediate A1 fixture shape change is required.

Three proposed enhancements:

1. TypeScript SDK quickstart parity: demo value 5, risk reduction 4, contract impact 1, estimated effort 3, API evidence value 3. Selected because TypeScript was the largest uncovered long-goal surface.
2. Queue worker facade for local cloud runtime: demo value 4, risk reduction 4, contract impact 2, estimated effort 4, API evidence value 2.
3. Hosted media semantics read-only calibration: demo value 3, risk reduction 4, contract impact 1, estimated effort 3, API evidence value 4; real media calls stayed blocked this round.

Subagent findings:

- Bus-Auditor: PASS for TypeScript quickstart parity as highest ROI; no real API calls; keep changes in A1-owned dirs; do not touch `services/judge`.
- Explorer-SDK/API: requested exact constants, `AgentInput`/`AgentTurn`/`RunResult`/cloud record types, `buildDefaultRequestInputSchema`, redaction, no-network tests, and optional TS agent demo. A2 `a6ee272` does not require immediate A1 fixture changes.
- Explorer-Chrome/Product: public docs still show TypeScript SDK references/tabs plus dataset/run/request/media boundary fields; Usage loaded without sign-in blocker but media counters were unstable in that pass.
- Worker-TS: began a JS+d.ts variant, then stopped when the main TypeScript-source package appeared. Main agent consolidated on TypeScript source compiled by `tsc`; the worker quickstart/test ideas were retained after redirecting them to `dist`.
- Reviewer: initial BLOCK for TS parity absent is resolved by this implementation; requested schema constants, redaction, no-network, and tests.

Implemented:

- `packages/ts/ashr-clone/package.json`, `package-lock.json`, `tsconfig.json`, `.gitignore`, and README.
- `packages/ts/ashr-clone/src/index.ts`: local-only TypeScript exports for `AGENT_INPUT_SCHEMA_VERSION`, `AGENT_TURN_SCHEMA_VERSION`, `RUN_RESULT_SCHEMA_VERSION`, `CLOUD_API_SCHEMA_VERSION`, `AgentInput`, `AgentTurn`, `RunResult`, cloud records, `QuotaLedger`, `InMemoryCloudStore`, `CloudApiService`, `buildDefaultRequestInputSchema`, `runAgentCloudDemo`, `coerceAgentInput`, `agentInputFromText`, `agentInputFromParts`, `redactText`, and `redactSensitive`.
- `packages/ts/ashr-clone/test/cloud-api.test.mjs` and `test/runtime.test.mjs`: 13 Node tests covering constants, AgentInput/media parts, request schema, redaction, no-network cloud flow, tenant isolation, quota blocking before writes, request media schema preservation, and TS agent demo fixture export.
- `packages/ts/ashr-clone/examples/quickstart.mjs`: imports an existing A1 run result JSON, submits it into TS `CloudApiService`, and writes a local cloud fixture.
- `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/api_calibration/README.md`, `docs/a1/evidence/commands.md`, `docs/evidence/official_site_gaps.md`, and this worklog were updated.

Verification:

- `node --version`: `v24.14.0`.
- `npm --version`: `11.9.0`.
- `tsc --version`: not globally installed; package devDependency supplies TypeScript.
- `npm install --prefix packages/ts/ashr-clone`: installed TypeScript dev dependency; 0 vulnerabilities.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 13 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 117 passed.
- `git diff --check`: no whitespace errors; Windows line-ending warnings only.
- Sensitive scan over intended files: matches were public env var names, private-evidence path references, package-lock public npm URL, and synthetic test tokens/emails/URLs only. No real key, secret file contents, or raw private evidence was read or staged.
- `node packages/ts/ashr-clone/examples/quickstart.mjs docs/a1/evidence/local_run_30.json docs/evidence/private_refs/a1_ts_quickstart_fixture_smoke.json`: wrote an ignored private 30-case fixture with `local_only=true`, `ashr_api_used=false`, and no hosted API calls.
- Final Bus-Auditor: PASS. Required staging boundary is six modified docs plus nine new `packages/ts/ashr-clone` files only; do not stage `dist/`, `node_modules/`, `.secrets/`, `.pytest_cache/`, or `docs/evidence/private_refs/`.
- Real API calls: none in this implementation round.

Remaining / next top 3:

1. Add a queue worker facade around the local cloud runtime so submitted runs can move through queued/running/completed states.
2. Add TypeScript API-client dry-run/transport-injected parity for read-only probes before any hosted TS calls.
3. Convert selected private hosted run evidence through the A2 Ashr grading import bridge into public-safe calibration observations.

Publish closure:

- Final staged scope: six A1/docs evidence files plus nine `packages/ts/ashr-clone` source/test/package files. Ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, `dist/`, and `node_modules/` stayed unstaged.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 13 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 117 passed.
- Staged path guard: no forbidden staged paths.
- Staged high-risk secret pattern scan: no `sk-...`, GitHub token, or bearer-token patterns found in staged files.

## 2026-07-04 Local Queue Worker Facade

Goal: add a local queue worker facade so cloud-runtime runs can be accepted as queued work, progress through queued/running/completed or failed states, preserve A3 fixture shape, and obey quota ledger phase boundaries without calling hosted Ashr APIs.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced from `2c43237` to `fe01f94`.
- `gh pr list --state all`: PR #6 remains open/draft on `codex/a1-local-sdk-runner`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, `packages/ts/ashr-clone/dist/`, and `node_modules/` present and unstaged.

Baseline scan:

- Existing A1 surfaces: Python SDK/Adapter/Runner/Trace/API probe, `AgentInput`, `services/api` local runtime, cloud demo CLI, TypeScript local SDK quickstart, MockAgent, A1 tests/docs/schemas, ignored private real API evidence.
- Existing cloud runtime before this round could create tenant/project/dataset/request records, submit completed run results, poll stored runs, export fixtures, and enforce quota checks.
- Missing before this round: queued run creation, worker-owned queued/running/completed transitions, timeout-safe queued demo behavior, queued CLI, and status history in cloud schema docs.
- Peer changes/impact: latest peer commit `fe01f94` added A2 grading merge gate files under A2 docs/fixtures/scripts plus `services/judge` and `tests/a2`. No A1-owned file impact; no Gate contract change required from A1.

Three proposed enhancements:

1. Queue worker facade: demo value 5, risk reduction 5, contract impact 2, estimated effort 3, API evidence value 2. Selected because queue lifecycle is an explicit phase target and makes the local cloud runtime closer to hosted run behavior.
2. TypeScript API-client dry-run/transport-injected parity: demo value 4, risk reduction 4, contract impact 1, estimated effort 4, API evidence value 4.
3. Public-safe A2 grading import from private hosted evidence: demo value 3, risk reduction 3, contract impact 2, estimated effort 3, API evidence value 3.

Subagent / auditor status:

- Reused existing subagent threads because the thread limit prevented spawning new ones. Four old threads initially returned empty completed states after requeue; this limitation is recorded as a tooling/evidence gap for the role protocol.
- Bus-Auditor final recheck succeeded after an explicit resend. Initial verdict: BLOCK because queued wait timeout could return a non-terminal poll and `run_agent_cloud_queue_demo(...)` would then write an incomplete fixture/run/summary and CLI could exit 0.
- Bus-Auditor required fix: require terminal status before writing queued demo outputs, add helper/CLI timeout regressions, and keep staging inside A1-owned dirs.
- Implemented the required fix and reran queue/full tests.

Implemented:

- `services/api/queue_worker.py`: added `QueueRunRequest`, `CloudQueueWorker`, queued background execution, max-worker normalization, poll/wait/cancel methods, terminal wait enforcement, and redacted failure handling.
- `services/api/runtime.py`: added queued run creation, running/completed/failed/cancelled transitions, `status_history`, phase-correct `run.submit` and `observation.write` quota consumption, and completion into the existing fixture/export shape.
- `services/runner/runner.py`: added optional `run_id` injection for queued runs so `RunResult` and observations share the cloud run id.
- `services/api/demo.py`: added `run_agent_cloud_queue_demo(...)`, which waits for terminal status before writing outputs.
- `services/api/cli.py`: added `run-agent-queued` with `--queue-workers`, `--wait-timeout`, and existing output/failure controls.
- `services/api/__init__.py`: exported queue worker symbols and queued demo helper.
- `tests/a1/test_cloud_api.py`: added queue transition/fixture/quota tests and observation-quota failure coverage.
- `tests/a1/test_cloud_api_cli.py`: added queued helper/CLI success tests and wait-timeout no-output regressions.
- `tests/a1/fixtures_sensitive_agent.py`: added `SlowAgent` for bounded wait-timeout regressions.
- `docs/a1/schemas/cloud_api.schema.json`: added `status_history` shape.
- `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/api_calibration/README.md`, `docs/a1/evidence/commands.md`, `docs/evidence/official_site_gaps.md`, and this worklog were updated.

Verification:

- Chrome docs check: official API reference showed `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `request_status`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, and `generate_files`.
- Chrome Usage check: `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but showed sign-in copy in this pass; `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` labels were not confirmed. No private counters recorded.
- Final remote recheck: PR #6 was merged; `origin/main` advanced to `e786c98` and contains prior A1 head `7c94460`. The current branch was fast-forwarded to `origin/main` before staging this round. Latest peer `4af23c4` added A2 case book regression seed files under A2 docs/fixtures/scripts plus `services/judge` and `tests/a2`; no A1-owned conflict after conflict resolution in `docs/evidence/official_site_gaps.md`.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 21 passed.
- `python -B -m pytest tests/a1/test_runner.py -q -p no:cacheprovider`: 19 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 123 passed.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 13 Node tests passed.
- `python -B -m services.api.cli run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples.agents.mock_agent:RespondingMockAgent --fixture-output docs/evidence/private_refs/a1_queue_demo_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_queue_demo_summary_smoke.json --run-output docs/evidence/private_refs/a1_queue_demo_run_smoke.json --tenant-id tenant_a1_queue_smoke --project-id project_a1_queue_smoke --dataset-id dataset_a1_queue_smoke --runner-id a1-queue-smoke --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure`: completed locally with 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, trace completeness 1.0, status history `queued -> running -> completed`, and quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- Real API calls: none in this implementation round.

Remaining / next top 3:

1. Add TypeScript API-client dry-run/transport-injected parity for read-only probes before any hosted TS calls.
2. Add queue persistence/replay controls so queued run state can survive process boundaries and produce deterministic replay artifacts.
3. Convert selected private hosted run evidence through the A2 Ashr grading import/merge bridge into public-safe calibration observations.

## 2026-07-04 TypeScript API Client Dry-Run Parity

Goal: add the hosted-parity TypeScript API client guardrail layer before any hosted TS calls, so TS developers can plan/read/probe Ashr API operations through the same dry-run-first, transport-injected discipline as the Python client.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced from `085c439` to `6efe390`.
- `gh pr list --state all`: PR #7 remains open/draft/mergeable on `codex/a1-local-sdk-runner` at `23b4af0`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, `packages/ts/ashr-clone/dist/`, and `node_modules/` present and unstaged.

Baseline scan:

- Existing A1 surfaces: Python SDK/Adapter/Runner/Trace/API probe, local cloud runtime, queue worker facade, cloud demo CLI, TypeScript local SDK quickstart, MockAgent, A1 tests/docs/schemas, and ignored private real API evidence.
- Existing TS package before this round exported local runtime/agent input/cloud/quota/redaction only. Its README explicitly said it did not expose hosted API client behavior yet.
- Peer changes/impact: latest peer `6efe390 G3: add A2 batch planning gate` touched `docs/a2`, `fixtures/a2`, `scripts/a2_regenerate_fixtures.py`, `services/judge`, `tests/a2`, and `docs/worklog/Kay.md`. No A1-owned conflict or Gate contract action required from A1.

Three proposed enhancements:

1. TypeScript API-client dry-run/transport parity: demo value 4, risk reduction 5, contract impact 1, estimated effort 3, API evidence value 5. Selected because it closes the largest remaining TS gap before any paid or real TS call.
2. Queue persistence/replay controls: demo value 4, risk reduction 4, contract impact 2, estimated effort 4, API evidence value 2.
3. Public-safe A2 grading import from private hosted evidence: demo value 3, risk reduction 3, contract impact 2, estimated effort 3, API evidence value 3.

Subagent / auditor status:

- Bus-Auditor: PASS for current implementation scope, but required evidence fixes before continuing: record peer drift to `6efe390`, update stale queue-worker next candidate, and keep ignored private evidence/build/cache paths out of staging.
- Explorer-SDK/API: confirmed Python API client/probe already provide the parity kernel and recommended a separate TS API-client layer with dry-run default, injected transport, env constants, redaction, request preflight, failed-request summaries, and tests.
- Explorer-Chrome: Chrome was available; public homepage/docs were reachable, lab usage was blocked by sign-in/onboarding in that subagent pass, and private screenshots/notes stayed under ignored private evidence.
- Worker-Runtime: fixed a queue cancellation edge case in `services/api/queue_worker.py`; `wait_for_run(...)` now returns terminal cancelled runs and handles cancelled executor futures. Added two tests in `tests/a1/test_cloud_api.py`.
- Worker-TS/Reviewer could not be spawned initially due to thread limit; main thread implemented the TS API-client work and covered it with focused Node tests.

Implemented:

- `packages/ts/ashr-clone/src/api-client.ts`: added `AshrApiClient`, `AshrApiError`, `MissingAshrApiKeyError`, `AshrApiCallPlan`, `AshrApiCallRecord`, `AshrApiTransport`, env/base-url constants, field-map version, dry-run call plans/records, injected transport execution, session context injection, read-only `init`/`healthCheck`/`listAgents`/dataset/run/request methods, mutating `createRun`/`createRequest` guardrails, `pollRun`/`pollRequest`, retry handling, API-level error redaction, media/non-text preflight summaries, and safe failed-request summary shapes.
- `packages/ts/ashr-clone/src/index.ts`: exported the API client layer.
- `packages/ts/ashr-clone/test/api-client.test.mjs`: added 11 Node tests covering dry-run no-fetch behavior, env construction without logging keys, injected transport execution, `keep_alive`, `list_agents`, missing-key guard, media schema dry-runs, mutation guardrails, retryable statuses, API error redaction, failed request summaries, and preflight helpers.
- `services/api/queue_worker.py` and `tests/a1/test_cloud_api.py`: incorporated Worker-Runtime's cancellation fix/regressions.
- `packages/ts/ashr-clone/README.md`, `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/api_calibration/README.md`, `docs/a1/evidence/commands.md`, `docs/evidence/official_site_gaps.md`, and this worklog were updated.
- Bus-Auditor final block: `pollRun({ dryRun:false })` and `pollRequest({ dryRun:false })` could bypass the normal `call(...)` missing-key guard through `pollUntil(...)` and reach injected transport with `Bearer null`. Fixed by guarding inside `AshrApiClient.request(...)` and adding regression tests that prove no transport call happens without a configured key.

Verification:

- Chrome main-thread check: `https://ashr.io/docs/api-reference/` returned `404 Not Found`; the correct public API reference is `https://ashr.io/docs/python-sdk/api-reference/`.
- Chrome API reference check: public page exposed `AshrLabsClient`, `health_check`, `list_agents`, `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, `generate_files`, `Trace`, `Span`, and `Generation`.
- Chrome Usage check: `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but showed sign-in copy in this pass; `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` labels were not confirmed. No private counters recorded.
- Private screenshot paths: `docs/evidence/private_refs/ashr_api_reference_ts_client_round_2026-07-04.png` and `docs/evidence/private_refs/ashr_usage_ts_client_round_2026-07-04.png`.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 24 Node tests passed after the missing-key poll fix.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 125 passed after the queue cancellation fix.
- Real API calls: none in this round. The desktop key file, `.secrets`, and private evidence contents were not read.

Remaining / next top 3:

1. Add queue persistence/replay controls so queued run state can survive process boundaries and produce deterministic replay artifacts.
2. Add a TypeScript probe CLI wrapper around the dry-run `AshrApiClient` before any hosted TS calls.
3. Convert selected private hosted run evidence through the A2 Ashr grading import/merge bridge into public-safe calibration observations.

## 2026-07-04 Queue Persistence And Replay CLI

Goal: turn the local queue persistence/replay library slice into an operator-facing loop: create a queued run state snapshot, reload it in a later process, replay incomplete queued/running runs through the local worker, write a completed state snapshot, and export A3-consumable run fixtures without calling hosted Ashr APIs.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success.
- `gh pr list --state all --limit 20`: PR #7 open/draft on `codex/a1-local-sdk-runner`; `gh pr view 7` later confirmed mergeable at head `c81e60d`.
- `git status -sb --untracked-files=all`: tracked in-progress files were `services/api/runtime.py`, `services/api/queue_worker.py`, and `tests/a1/test_cloud_api.py`; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, and TS build/cache paths remained unstaged.

Baseline scan:

- Existing A1 surfaces: Python SDK/Adapter/Runner/Trace/API probe, local cloud runtime, queue worker facade, cloud demo CLI, TypeScript local SDK and hosted dry-run client, MockAgent, A1 tests/docs/schemas, ignored private real API evidence.
- Existing persistence work at round start: `CloudApiService.snapshot_state(...)`, `write_state(...)`, `from_state_file(...)`, `CloudQueueWorker.replay_incomplete_runs(...)`, and library tests for state roundtrip and replay.
- Missing before this round: operator CLI controls for state input/output, persisted queued-state creation, replay from restored state across subprocess boundaries, and guarded fixture export from restored state.
- Peer changes/impact: latest peer `007c650 G3: add A2 semantic judge harness` touched A2 docs/worklog/fixtures/scripts plus `services/judge` and `tests/a2`. No A1-owned conflict; do not integrate/rebase in a way that drops those peer files.

Three proposed enhancements:

1. Queue persistence/replay CLI controls: demo value 5, risk reduction 5, contract impact 1, estimated effort 2, API evidence value 2. Selected because it makes the newly available persistence/replay core useful to A2/A3 and fresh setup.
2. TypeScript probe CLI wrapper around dry-run `AshrApiClient`: demo value 4, risk reduction 4, contract impact 1, estimated effort 3, API evidence value 4.
3. Public-safe A2 grading import from selected hosted evidence: demo value 3, risk reduction 3, contract impact 2, estimated effort 3, API evidence value 3.

Subagent / auditor status:

- Bus-Auditor: PASS for local-only queue persistence/replay next; required updating stale PR/peer evidence to PR #7 head `c81e60d` and peer `007c650`, and preserving secret/private evidence hygiene.
- Explorer-SDK/API: recommended TS probe CLI as a future high-ROI item, but also confirmed queue persistence/replay already had library coverage and needed CLI/product controls.
- Explorer-Chrome: Chrome subagent could not stably claim lab tabs and made no credential/API calls; main thread completed the read-only Chrome check.
- Worker-Runtime: implemented the bounded library slice for state snapshot/load and replay incomplete runs; main thread extended it to CLI/demo/fixture-export controls.
- Reviewer / Worker-TS: not separately spawned at first because the thread limit was reached; main thread covered the selected Python CLI path with focused and full regression tests.

Implemented:

- `services/api/demo.py`: added optional `state_output_path` for direct and queued demos; added `create_agent_cloud_queue_state(...)`, `replay_agent_cloud_queue_state(...)`, and `export_run_fixture_from_state(...)`; added terminal-status guard so restored queued/running state cannot be exported as a completed fixture unless explicitly allowed.
- `services/api/cli.py`: added `queue-run`, `replay-queued`, and `export-fixture`; added `--state-output` to `run-agent` and `run-agent-queued`.
- `services/api/__init__.py`: exported the new demo helpers.
- `tests/a1/test_cloud_api_cli.py`: added subprocess roundtrip coverage for `queue-run -> replay-queued -> export-fixture` and a regression that incomplete queued state cannot be exported by default.
- `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, `docs/a1/evidence/commands.md`, and this worklog were updated.

Verification:

- Chrome main-thread check: `https://ashr.io/docs/python-sdk/api-reference/` exposed `AshrLabsClient`, `health_check`, `list_agents`, `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, and `generate_files`.
- Chrome Usage check: `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` and showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact private counters were not recorded.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 28 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 130 passed.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 24 Node tests passed.
- `python -B -m services.api.cli queue-run --input docs/a1/evidence/local_agent_cases_30.json --state-output docs/evidence/private_refs/a1_queue_state_snapshot_smoke.json --summary-output docs/evidence/private_refs/a1_queue_state_summary_smoke.json --tenant-id tenant_a1_replay_smoke --project-id project_a1_replay_smoke --dataset-id dataset_a1_replay_smoke --runner-id a1-replay-smoke --run-id run_a1_replay_smoke`: wrote ignored queued local state, 30 cases, `queued` status, `run.submit=1`.
- `python -B -m services.api.cli replay-queued --state-input docs/evidence/private_refs/a1_queue_state_snapshot_smoke.json --agent examples.agents.mock_agent:RespondingMockAgent --tenant-id tenant_a1_replay_smoke --project-id project_a1_replay_smoke --dataset-id dataset_a1_replay_smoke --fixture-output docs/evidence/private_refs/a1_queue_replay_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_queue_replay_summary_smoke.json --run-output docs/evidence/private_refs/a1_queue_replay_run_smoke.json --state-output docs/evidence/private_refs/a1_queue_replayed_state_smoke.json --max-runs 1 --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30`: completed with 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, trace completeness 1.0, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`, status history `queued -> running -> completed`.
- `python -B -m services.api.cli export-fixture --state-input docs/evidence/private_refs/a1_queue_replayed_state_smoke.json --tenant-id tenant_a1_replay_smoke --project-id project_a1_replay_smoke --run-id run_a1_replay_smoke --fixture-output docs/evidence/private_refs/a1_queue_exported_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_queue_export_summary_smoke.json`: exported a completed run fixture from restored state.
- Final remote recheck before staging: `origin/dev/g3-a2-calibration` advanced from `007c650` to `18e4a96 G3: add A2 semantic judge import bridge`, touching `docs/a2`, `docs/worklog/Kay.md`, `fixtures/a2/calibration`, `scripts/a2_import_semantic_judge.py`, `scripts/a2_merge_calibration_observations.py`, `services/judge`, and `tests/a2`. No A1-owned conflict observed; current branch remained even with `origin/codex/a1-local-sdk-runner`.
- Real Ashr API calls: none in this implementation round. No env key, `.secrets`, desktop key file, or raw private evidence contents were read.

Remaining / next top 3:

1. Add TypeScript probe CLI wrapper around dry-run `AshrApiClient` for cross-language API calibration ergonomics.
2. Add persistent queue batch controls for multiple queued runs with deterministic replay ordering and summary export.
3. Convert selected private hosted run evidence through the A2 grading import/merge bridge into public-safe calibration observations after explicit evidence-selection rules.

## 2026-07-04 TypeScript Probe CLI

Goal: add a dry-run-first TypeScript probe CLI around the hosted-parity `AshrApiClient`, so TS users get the same operator ergonomics as Python `services.runner.api_probe`: plan/read/probe calls without keys by default, write redacted JSON records, require explicit execution/mutation flags, and keep real Ashr API usage under the dry-run -> small batch -> batch rule.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced from `18e4a96` to `8542b19`, and `origin/codex/a3-p3-ashr-calibration` advanced from `c30b67a` to `5872ef3`.
- `gh pr list --state all --limit 30`: PR #7 open/draft on `codex/a1-local-sdk-runner` at `7942516`; prior A1 PRs merged.
- `git status -sb --untracked-files=all`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, TS `dist/`, and `node_modules/` remained unstaged.

Baseline scan:

- Python A1 surfaces: SDK adapter/types/trace/dataset adapter/API client, runner CLI, Python API probe, local cloud runtime/queue/replay CLI, MockAgent, A1 tests/schemas/docs.
- TypeScript surfaces: `packages/ts/ashr-clone` exports local SDK/runtime/quota/redaction plus hosted dry-run `AshrApiClient`; tests cover API client library parity, but package metadata has no `bin` or probe CLI yet.
- Private evidence: many ignored `docs/evidence/private_refs/a1_api_*`, queue smoke, TS quickstart, and Chrome screenshot/note files exist; only filenames were listed, raw contents were not read.
- Known gaps: hosted TS auth/quota/media behavior remains unverified; no TS operator CLI exists; hosted queue persistence/cancellation semantics remain local-only; request generation quota was previously exhausted/unclear for additional create-request calls.
- Peer changes/impact: A2 latest `8542b19 G3: add A2 regression replay evidence` touched A2 docs/fixtures/scripts plus `services/judge` and `tests/a2`; A3 latest `5872ef3 Add A3 product console media evidence` touched dashboard/report/A3 docs/screenshots/fixtures/tests. No A1-owned conflict; do not stage or alter A2/A3/judge/dashboard changes.

Three proposed enhancements:

1. TypeScript probe CLI wrapper around dry-run `AshrApiClient`: demo value 5, risk reduction 5, contract impact 1, estimated effort 3, API evidence value 5. Selected because it converts existing TS library parity into an operator/fresh-setup surface without real API calls by default.
2. Persistent queue batch controls for multiple queued runs: demo value 4, risk reduction 4, contract impact 1, estimated effort 3, API evidence value 2.
3. Public-safe A2/A3 calibration bridge from selected hosted evidence: demo value 4, risk reduction 3, contract impact 2, estimated effort 4, API evidence value 4.

Round-start subagents:

- Bus-Auditor, Explorer-SDK/API, Explorer-Chrome, and Worker-TS were spawned. Runtime/Reviewer could not be spawned initially because the agent thread limit was reached; main thread will retry after an agent finishes.
- Bus-Auditor initial verdict: BLOCK until the TS probe CLI draft stopped printing full real records to stdout, defaulted to ignored private evidence output, and wrote redacted error records for failures.
- Explorer-SDK/API: confirmed the exact TS CLI surface should mirror Python `services.runner.api_probe` operations and flags, with `health-check -> keep_alive`, dry-run `poll-run -> poll_run`, real polling through `get_run`, and create-request summary-shaped params.
- Explorer-Chrome: verified public TypeScript API/auth docs plus Usage labels. TS API docs showed `AshrLabsClient`, `fromEnv`, run/request APIs, `healthCheck`, accepted input and media generation fields; TS docs did not show `generate_images`, `listAgents`, or `pollRun` in that pass.
- Worker-TS: created the first `src/probe.ts`, package bin/script, and probe tests. Main thread retained the structure, then tightened stdout/error-record safeguards per Bus-Auditor.

Implemented:

- `packages/ts/ashr-clone/src/probe.ts`: added dry-run-first API probe CLI with Python-parity operations, env-only key loading, mutating execution gates, media/non-text/variation guardrails, default ignored private evidence output paths, one-line stdout summaries by default, opt-in `--print-record`, output-file JSON writing, and redacted error-record persistence.
- `packages/ts/ashr-clone/test/probe.test.mjs`: added CLI tests for dry-run no-network behavior, output-file writing, `--print-record`, read-only operation mapping, create-request preflight shape summaries, create-run dry-run plans, missing-key handling, mutating guardrails, and media guard blocking before transport.
- `packages/ts/ashr-clone/package.json` and `package-lock.json`: added `ashr-clone-probe` / `ashr-clone-api-probe` bin entries, `npm run probe`, and Node types for CLI compilation.
- `packages/ts/ashr-clone/README.md`, `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/explorer_sdk.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, `docs/a1/evidence/commands.md`, and this worklog were updated.

Verification:

- `npm install --package-lock-only --prefix packages/ts/ashr-clone`: up to date, 0 vulnerabilities.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 33 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 130 passed.
- `node packages/ts/ashr-clone/dist/probe.js init --output docs/evidence/private_refs/a1_ts_api_init_dry_run.json`: planned dry-run, wrote ignored private evidence, stdout summary only.
- `node packages/ts/ashr-clone/dist/probe.js create-request --request-name "A1 TS Media Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_ts_api_media_create_request_dry_run.json`: planned dry-run for Image/Audio/Files interface, wrote ignored private evidence, stdout summary only.
- Final remote recheck before staging: `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` from `8542b19` to `1cc07a7 G3: deepen A2 media API calibration` and `origin/codex/a3-p3-ashr-calibration` from `5872ef3` to `02f6ce7 Add A3 tool call diff panel`. Peer changes stayed in A2/A3 docs/fixtures/tests plus `services/judge`, `services/report`, and `apps/dashboard`; no A1-owned conflict observed.
- Final validation: `npm test --prefix packages/ts/ashr-clone` passed 33 Node tests; `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed 130 tests; `git diff --check` exited 0 with only CRLF warnings.
- Public-file secret scan: `rg` checks for desktop key paths, local key filenames, GitHub-token prefixes, model-key prefixes, and bearer-token literals in intended TS/A1 docs files found no matches.
- Real Ashr API calls: none in this implementation round. No env key, `.secrets`, desktop key file, or raw private evidence contents were read.

Remaining / next top 3:

1. Add persistent queue batch controls for multiple queued runs with deterministic replay ordering and summary export.
2. Convert selected private hosted run evidence through the A2/A3 calibration import bridges into public-safe observations after explicit evidence-selection rules.
3. Add optional TypeScript injected-transport probe fixtures for API-level error/quota header shapes before any hosted TS execution.

## 2026-07-04 Queue Batch Replay Controls

Goal: extend the local cloud queue/replay path from a single queued run into a batch-capable operator loop: one state snapshot can hold multiple queued runs, replay uses deterministic batch order, summaries expose every run and status history, and A2/A3 can consume per-run fixture/result outputs without relying on hosted Ashr APIs.

Start protocol:

- `pwd`: `C:\Users\33516\Documents\Ashr`.
- `git rev-parse --show-toplevel`: `C:/Users/33516/Documents/Ashr`.
- `git remote -v`: origin is `https://github.com/3351666087/ashr-codex-factory`.
- `gh repo view`: repo `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success, no fetch output in this pass.
- `gh pr list --state all --limit 30`: PR #7 open/draft on `codex/a1-local-sdk-runner` at `4163a5e`; PR #8 open/draft for A3 at `02f6ce7`.
- `git status -sb --untracked-files=all`: tracked worktree clean at round start.

Baseline scan:

- A1 surfaces present: Python SDK/Adapter/Runner/Trace/API probe, local cloud runtime/queue/replay CLI, TypeScript local SDK and hosted dry-run API/probe, tests/schemas/docs, and ignored private evidence filenames.
- Private evidence filenames include prior real API probes, queue smoke outputs, TS dry-run probes, and Chrome screenshots; raw contents were not read.
- Current process has neither `ASHR_API_KEY` nor `ASHR_LABS_API_KEY`, so live hosted API work is blocked this round. The desktop key file, `.secrets`, and raw private evidence contents were not read.
- Peer changes/impact: `origin/dev/g3-a2-calibration` remains at `1cc07a7` and `origin/codex/a3-p3-ashr-calibration` remains at `02f6ce7`; peer-owned changes are A2/A3/judge/dashboard/report scoped with no A1-owned conflict observed.

Three proposed enhancements:

1. Persistent queue batch controls for multiple queued runs with deterministic replay ordering and summary export: demo value 5, risk reduction 5, contract impact 1, estimated effort 2, API evidence value 2. Selected because it directly upgrades the existing queue/replay CLI into a batch-capable A2/A3 handoff path.
2. TypeScript local runner/adapter body (`AgentAdapter`, `runAgentBatch`, `LocalEvalRunner`, CLI): demo value 5, risk reduction 4, contract impact 1, estimated effort 4, API evidence value 2.
3. TypeScript injected-transport probe fixtures for API-level error/quota headers: demo value 3, risk reduction 4, contract impact 1, estimated effort 2, API evidence value 3.

Subagents:

- Bus-Auditor: PASS for local-only queue batch controls; BLOCK for live hosted API calls due to missing env keys; BLOCK for A2/A3 hosted-evidence bridge until public-safe evidence selection rules exist.
- Explorer-SDK/API: no code edits; confirmed TS still lacks the Python-sized adapter/runner/dataset/trace/queue CLI body, and recommended TS local runner/adapter as the next high-ROI TS growth slice after this queue batch round.
- Explorer-Chrome subagent ran against unrelated OpenAI docs, so its result is not used as Ashr evidence.
- Worker-Runtime: provided partial queue batch edits for deterministic replay ordering, batch queue summaries, and per-run output helpers; main thread completed CLI wiring, tests, docs, and smoke validation.

Official / Chrome check:

- Main-thread Chrome verified `https://ashr.io/docs/typescript-sdk/api-reference/` and `https://ashr.io/docs/python-sdk/api-reference/`.
- TypeScript docs exposed `AshrLabsClient`, `fromEnv`, `createRun`, `getRun`, `listRuns`, `deleteRun`, `createRequest`, `getRequest`, `listRequests`, `waitForRequest`, `generateDataset`, `healthCheck`, `Trace`, `Span`, `Generation`, `accepted_inputs`, `generate_audio`, and `generate_files`.
- Python docs also exposed `generate_images`, `generate_audio`, and `generate_files`; TS docs still did not show `generate_images` in this pass.
- `https://lab.ashr.io/?tab=usage` initially showed `Loading Usage...`, then settled to `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`. Exact private counter values were not recorded in tracked docs. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_queue_batch_round_2026-07-04.png`.

Implemented:

- `services/api/demo.py`: `create_agent_cloud_queue_state(...)` now accepts repeated/explicit `run_ids` and generated `run_count`, records `batch_index`, `batch_size`, and `replay_order`, summarizes all queued run IDs/status histories, replays up to 100 runs by default, and writes per-run fixture/result maps through `fixture_output_dir` / `run_output_dir`.
- `services/api/cli.py`: `queue-run --run-id` is repeatable, `queue-run --run-count` creates generated run IDs when explicit IDs are absent, and `replay-queued` supports `--fixture-output-dir` / `--run-output-dir`.
- `services/api/queue_worker.py`: replay candidates sort by `metadata.replay_order` / `batch_index`, then `created_at`, then `run_id`; replayed runs receive normalized `queue_workers` and `runner_max_workers` metadata.
- `tests/a1/test_cloud_api.py`: added deterministic batch-order replay coverage.
- `tests/a1/test_cloud_api_cli.py`: added multi-run CLI replay/export coverage and singleton output guardrail coverage.
- `docs/a1/README.md`, `docs/a1/api_calibration/README.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, `docs/a1/evidence/commands.md`, and this worklog were updated.

Verification:

- `python -B -m py_compile services/api/demo.py services/api/queue_worker.py services/api/cli.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py`: passed.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 31 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 33 Node tests passed.
- `git diff --check`: exited 0 with only CRLF warnings.
- `python -B -m services.api.cli queue-run --input docs/a1/evidence/local_agent_cases_30.json --state-output docs/evidence/private_refs/a1_queue_batch_state_snapshot_smoke.json --summary-output docs/evidence/private_refs/a1_queue_batch_state_summary_smoke.json --tenant-id tenant_a1_batch_replay_smoke --project-id project_a1_batch_replay_smoke --dataset-id dataset_a1_batch_replay_smoke --runner-id a1-batch-replay-smoke --run-id run_a1_batch_replay_002 --run-id run_a1_batch_replay_001`: wrote ignored local batch state with two queued 30-case runs, explicit order, `dataset.create=1`, and `run.submit=2`.
- `python -B -m services.api.cli replay-queued --state-input docs/evidence/private_refs/a1_queue_batch_state_snapshot_smoke.json --agent examples.agents.mock_agent:RespondingMockAgent --tenant-id tenant_a1_batch_replay_smoke --project-id project_a1_batch_replay_smoke --dataset-id dataset_a1_batch_replay_smoke --fixture-output-dir docs/evidence/private_refs/a1_queue_batch_replay_fixtures --summary-output docs/evidence/private_refs/a1_queue_batch_replay_summary_smoke.json --run-output-dir docs/evidence/private_refs/a1_queue_batch_replay_runs --state-output docs/evidence/private_refs/a1_queue_batch_replayed_state_smoke.json --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30`: replayed two runs in deterministic batch order; each completed 30 passed, 0 failed, 0 errored, 0 timed out, with 60 observations; total quota used `dataset.create=1`, `run.submit=2`, `observation.write=120`; per-run fixture/result files were written under ignored private evidence.
- Final remote recheck before audit: `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` to `ea1039a G3: surface A2 evidence readiness in A3 reports` and `origin/codex/a3-p3-ashr-calibration` to `e39b823 Merge latest main into A3 product console PR`. Direct new peer paths were A2 docs/worklog/fixtures/scripts/judge/tests and A3 dashboard/report/tests; no A1-owned working tree conflict or staged peer files observed.
- Real Ashr API calls: none in this round because env keys were absent and local key files remain unread.

Remaining / next top 3:

1. Add a TypeScript local runner/adapter slice (`AgentAdapter`, `runAgentBatch`, `LocalEvalRunner`, and an `ashr-clone-runner` CLI) so TS begins matching Python SDK/Runner body, not only API probe parity.
2. Add TypeScript injected-transport probe fixtures for API-level error/quota header shapes and hostile token-bearing error redaction coverage.
3. Convert selected private hosted run evidence through A2/A3 calibration import bridges after explicit public-safe evidence selection rules.

## 2026-07-04 TypeScript Runner/Dataset/Trace Parity

Goal: respond to the updated long-term A1 objective by making TypeScript much closer to Python in actual SDK/Runner body, not only API-client parity. This round implemented the top 5 ROI items from the new top-10 list: TS local runner/adapter/CLI, TS dataset-source adapter, strict trace/replay helpers, dataset adapter CLI, and Python-style literal batch/A2 projection helpers.

Start/baseline:

- Repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`.
- PR #7 for prior A1 work is merged; branch still has unmerged A1 head work and needs a new PR after this round.
- A1 Python surfaces were already present: SDK adapter/types/trace/dataset adapter/API client, runner CLI, cloud API/queue/replay CLI, tests/docs/schemas.
- TS surfaces at start had cloud/API/probe parity but lacked Python-sized local runner, strict trace helpers, dataset adapter CLI, and A2 projection.
- Env key presence: `ASHR_API_KEY=false`, `ASHR_LABS_API_KEY=false`; no real hosted calls were attempted.

Top 10 and decisions:

1. TS local runner/adapter/CLI: implemented.
2. TS dataset-source adapter: implemented.
3. TS strict trace/replay helpers: implemented.
4. TS dataset adapter CLI: implemented.
5. TS `runCase`/`runBatch`/`BatchRunner` and `toA2JudgeRun`: implemented.
6. TS cloud queue/replay parity: deferred.
7. TS quota/error injected fixture pack: deferred.
8. Real API read-only batch when env key exists: blocked by absent env key.
9. Hosted media failure shape calibration: deferred; no blind mutating retry.
10. TS docs/fresh setup polish: partially implemented through README/field map/worklog updates.

Subagents:

- Bus-Auditor: PASS for TS local runner/adapter as highest-ROI next slice; warned that current branch needs a new PR because PR #7 is merged, and no live API work should run without env keys.
- Explorer-SDK/API: confirmed current TS runner/dataset files and remaining gaps; recommended strict trace exports, dataset adapter CLI, runner breadth, A2 projection, and docs. These were addressed.
- Explorer-Chrome/Product: verified public TS/Python docs fields and logged-in Usage labels without recording private counters. Private screenshot: `docs/evidence/private_refs/ashr_lab_usage_ts_python_parity_2026-07-04.png`.
- Worker-TS: implemented the core `runner.ts` slice; main thread integrated and extended it.

Implemented:

- `packages/ts/ashr-clone/src/runner.ts`: `AgentAdapter`, `AgentResult`, `LocalEvalRunner`, `BatchRunner`, `runAgentBatch`, `runCase`, `runBatch`, `runFile`, `runAgentFile`, `buildRunFixture`, `buildCloudRunFixture`, `loadAgentTarget`, `coerceRunnerAgentInput`, `toA2JudgeRun`.
- `packages/ts/ashr-clone/src/runner-cli.ts`: `ashr-clone-runner` CLI.
- `packages/ts/ashr-clone/src/dataset-adapter.ts`: dataset-source extraction/case conversion/replay fixture helpers.
- `packages/ts/ashr-clone/src/dataset-adapter-cli.ts`: `cases` and `replay-fixture` commands.
- `packages/ts/ashr-clone/src/trace.ts`: `TraceRecorder`, strict trace event and VM frame validation, run fixture build/load/write helpers.
- `examples/agents/mock_agent_ts.mjs`: TS mock agent for local 30-case smoke.
- `packages/ts/ashr-clone/test/runner.test.mjs`, `dataset-adapter.test.mjs`, `trace.test.mjs`: focused Node tests.
- Docs updated in TS README, A1 README, field map, official site gaps, command log, and this worklog.

Verification:

- `npm install --package-lock-only --prefix packages/ts/ashr-clone`: up to date, 0 vulnerabilities.
- `npm test --prefix packages/ts/ashr-clone`: 47 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `node packages/ts/ashr-clone/dist/runner-cli.js --input docs/a1/evidence/local_agent_cases_30.json --output docs/evidence/private_refs/a1_ts_runner_run_30_smoke.json --agent examples/agents/mock_agent_ts.mjs:default --dataset-id a2-local-scenarios-ts --runner-id a1-ts-local-runner --run-id run_a1_ts_runner_30_smoke --max-workers 4 --timeout 5 --fixture-output docs/evidence/private_refs/a1_ts_runner_fixture_30_smoke.json --fail-on-case-failure`: 30 passed, trace completeness 1.0.

Known gaps / next top 10:

1. Open a new PR for current A1 branch work because PR #7 is merged.
2. Add TS cloud queue/replay parity against Python `services/api` queue state flows.
3. Add TS injected-transport quota/error fixture pack and hostile-token redaction cases.
4. When env key exists, run dry-run -> small real read-only hosted TS probes and record redacted private evidence.
5. Add TS strict fixture validation against Python schema snapshots where safe.
6. Add TS media/video envelope extension once official TS `video` naming is reconciled with local Image/Audio/File envelope.
7. Add public-safe A2/A3 hosted evidence bridge rules.
8. Add TS cloud runtime snapshot/replay persistence if queue parity requires it.
9. Add fresh setup script that runs Python + TS smoke in one command.
10. Recheck official docs/Usage after any hosted API calibration; do not record private counter values.

## 2026-07-05 TypeScript Cloud Queue And Five-Modality Envelope

Goal: continue the A1 long-term TS parity push by making TypeScript cover local cloud queue/state/replay flows and treating `text`, `audio`, `file`, `image`, and `video` as same-level AgentInput/request-schema modalities.

Baseline:

- Repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` and `origin/main` to `305939b`; PR #9 was already merged.
- The branch was fast-forwarded to `origin/main` before final validation, then the A1 work-in-progress was reapplied without conflicts.
- Peer impact: latest main/A2/G3 changes touched A2 docs/fixtures/judge/report/dashboard test paths, not A1 TS owned paths.
- Env presence: `ASHR_API_KEY=false`, `ASHR_LABS_API_KEY=false`, `ASHR_LABS_BASE_URL=false`; no real hosted API calls were made and no local key files were read.

Top 10 and decisions:

1. TS cloud queue/replay parity: implemented.
2. Five-modality `AgentInput` and request schema parity: implemented.
3. TS cloud CLI fresh setup path: implemented.
4. TS quota/state restore tests: implemented.
5. TS media dry-run fixture with video: implemented.
6. TS injected-transport hosted quota/error fixture pack: deferred.
7. Real TS hosted read-only probes when env keys exist: blocked by absent env keys.
8. Public-safe A2/A3 hosted evidence bridge rules: deferred.
9. One-command Python + TS smoke script: deferred.
10. Authenticated dashboard usage counter calibration: unverified.

Subagents:

- Bus-Auditor: PASS for staging/commit/push after rerunning TS/Python tests and `git diff --check`; noted this is local-only TS cloud/media parity, not hosted backend validation.
- Explorer-Chrome/Product: confirmed TS docs expose accepted inputs `text`, `audio`, `file`, `image`, and `video`; TS docs still did not expose `pollRun`, `listAgents`, `generate_images`, or `generate_videos` in the observed pass. Python docs continue to expose the missing media/run/list fields.
- Explorer-SDK/API initially failed in the prior pass due model capacity; a follow-up explorer was spawned for SDK/API review.
- Worker-TS and Reviewer were spawned after interruption for focused follow-up review.

Implemented:

- `packages/ts/ashr-clone/src/cloud-queue.ts`: `CloudQueueWorker`, `QueueRunRequest`, terminal statuses, deterministic replay ordering, queued/running/completed/failed/cancelled lifecycle execution, polling, cancellation, and redacted failures.
- `packages/ts/ashr-clone/src/cloud-cli.ts`: `ashr-clone-cloud` commands `queue-run`, `replay-queued`, and `export-fixture`, including repeated `--run-id`, `--run-count`, per-run fixture/result directories, restored-state export, and multi-run singleton-output guardrails.
- `packages/ts/ashr-clone/src/index.ts`: `video` in `AgentInputPartType`, cloud state snapshot/restore, quota state serialization, queued run lifecycle methods, status history, fixture/state file writing, and deterministic clock option.
- `packages/ts/ashr-clone/src/api-client.ts`, docs schemas, and media fixture now cover `text`, `audio`, `file`, `image`, and `video` consistently for dry-run request schema summaries.
- `packages/ts/ashr-clone/test/cloud-queue.test.mjs` plus existing TS tests cover queue replay, state restoration, CLI queue/replay/export, five-modality envelopes, and media dry-run summaries.

Verification recorded before final post-interruption rerun:

- `npm run build --prefix packages/ts/ashr-clone`: passed.
- `npm test --prefix packages/ts/ashr-clone`: 50 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `node packages/ts/ashr-clone/dist/cloud-cli.js queue-run ...`: wrote two queued 30-case TS cloud runs under ignored private evidence.
- `node packages/ts/ashr-clone/dist/cloud-cli.js replay-queued ...`: replayed both queued runs; each completed 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, status history `queued -> running -> completed`; total quota used `dataset.create=1`, `run.submit=2`, `observation.write=120`.
- `node packages/ts/ashr-clone/dist/cloud-cli.js export-fixture ...`: exported a completed restored-state fixture.
- `node packages/ts/ashr-clone/dist/probe.js create-request --request-name "A1 TS Media Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_ts_api_media_create_request_dry_run.json`: planned Text/Audio/File/Image/Video dry-run; no key or network call.

Next top 10:

1. Add TS injected-transport quota/error fixture pack with hostile-token redaction cases.
2. Add schema snapshot validation between TS fixtures and Python/A1 JSON schemas.
3. Add a one-command Python + TS fresh setup smoke script.
4. Define public-safe A2/A3 hosted evidence bridge rules before importing private run evidence.
5. Add TypeScript OpenAI-style adapter helpers for chat/completions-style agents.
6. Add tenant/project quota ledger persistence examples beyond in-memory JSON state.
7. Add TS cloud queue cancellation CLI coverage for persisted states.
8. When env-only API keys are present, run minimal authenticated read-only hosted TS probes and record redacted private evidence.
9. Recheck TS docs for `generate_images`, `generate_videos`, `pollRun`, and `listAgents` before mapping hosted names as official TS behavior.
10. Add public README matrix comparing Python and TypeScript parity surfaces.

### 2026-07-05 follow-up after SDK/API review

- Explorer-SDK/API found that TS had five-modality `AgentInput` parity, but Python SDK/default request-schema constants still omitted `video`, and TS cloud CLI lacked Python's one-shot `run-agent-queued` command.
- Fixed Python SDK drift in `packages/sdk/ashr_clone/adapter.py`, `packages/sdk/ashr_clone/api_client.py`, and `services/runner/api_probe.py`: `video` now participates in `AgentInput` validation, default request schema media part enums, and create-request preflight `agent_input_part_types`.
- Updated Python tests in `tests/a1/test_api_client.py` and `tests/a1/test_cloud_api.py` to require `video` in media schemas and preflight summaries.
- Added TS `ashr-clone-cloud run-agent-queued` one-shot CLI parity with `--fixture-output`, `--run-output`, `--summary-output`, `--state-output`, tenant/project/dataset names, `--no-timeout`, queue workers, max workers, wait timeout, and fail-on-case-failure behavior.
- Added TS CLI regression coverage proving one-shot queued run output writes fixture/run/state/summary and preserves tenant/project/dataset display names.
- Focused verification: `node --test packages/ts/ashr-clone/test/cloud-queue.test.mjs` passed 5 tests after `npm run build --prefix packages/ts/ashr-clone`; `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_cloud_api.py -q -p no:cacheprovider` passed 67 tests.

### 2026-07-05 final verification before staging

- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 52 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `node packages/ts/ashr-clone/dist/cloud-cli.js run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_cloud_one_shot_fixture_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_cloud_one_shot_run_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_one_shot_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_one_shot_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_one_shot --project-id project_a1_ts_cloud_one_shot --tenant-name "A1 TS Cloud One Shot Tenant" --project-name "A1 TS Cloud One Shot Project" --dataset-id dataset_a1_ts_cloud_one_shot --dataset-name "A1 TS Cloud One Shot Dataset" --runner-id a1-ts-cloud-one-shot --run-id run_a1_ts_cloud_one_shot --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure`: completed one 30-case queued TS run, wrote ignored fixture/run/summary/state evidence, and used quota `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `git diff --check`: exit 0 with CRLF warnings only.

## 2026-07-05 TypeScript Full Test Parity Sprint

Goal: respond to the A1 owner request to stop incremental TS catch-up and make TypeScript match the Python A1 test body directly. This round focused on TS SDK/cloud/runtime/CLI parity without reading or storing local key files and without hosted Ashr calls.

Baseline and peer state:

- Repo root: `C:/Users/33516/Documents/Ashr`; branch: `codex/a1-local-sdk-runner`; remote: `3351666087/ashr-codex-factory`; default branch: `main`.
- Commands run first: `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `git status -sb`; `gh repo view --json nameWithOwner,defaultBranchRef,url`; `gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,updatedAt,url`.
- PR state: PRs #1-#9 are merged; latest merged A1 PR #9. No open remote PR was observed in the fetched list.
- Worktree already contained the previous A1 TS cloud queue/video parity changes; this sprint continued on top of that dirty A1-owned tree.
- Peer changes/impact: none newly observed in A1-owned files after fetch; current changes are local A1/TS/Python/docs work. `docs/evidence/private_refs/` stayed ignored and was not staged/read for payload content.

Top 10 and decision:

1. Raise TS test runner from 52-ish executed tests to Python-scale 133: implemented.
2. Add direct TS cloud `run-agent` CLI parity with Python `services.api.cli run-agent`: implemented.
3. Keep queued TS cloud one-shot and persisted queue replay: preserved and revalidated.
4. Expand TS CloudApiService/quota/state/fixture failure-path tests: implemented.
5. Expand first-class `text/audio/file/image/video` tests: implemented.
6. Add more real API probes: deferred because no `ASHR_API_KEY` / `ASHR_LABS_API_KEY` env vars were present; no key files were read.
7. Add TS schema snapshot validation against JSON schemas: deferred.
8. Add TS hosted injected-transport quota/error fixture pack: deferred.
9. Add fresh setup one-command demo script combining Python + TS: deferred.
10. Update evidence and re-run Bus-Auditor: in progress at time of this log entry.

Implemented:

- `packages/ts/ashr-clone/src/cloud-cli.ts`: added direct `run-agent` command, `runAgentBatch` submission to `CloudApiService`, fixture/run/summary/state outputs, `--no-timeout`, `--fail-on-case-failure`, and Python-style `cloud api error:` exit path with code 2.
- `packages/ts/ashr-clone/test/parity-expansion.test.mjs`: new broad parity file covering five modalities, schema helper behavior, CloudApiService tenant/project/dataset/request/run lifecycle, quota ledger, state roundtrip, defensive copy behavior, queued run failure/cancel paths, direct cloud CLI smoke, error paths, and queue-run duplicate guardrails.
- Existing TS cloud queue/direct CLI tests now include direct `run-agent` parity and queued one-shot parity.

Validation:

- `npm test --prefix packages/ts/ashr-clone`: passed, `133` Node test items executed, `133` passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: passed, `133 passed in 9.80s`.
- `node packages/ts/ashr-clone/dist/cloud-cli.js run-agent --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_cloud_direct_fixture_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_cloud_direct_run_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_direct_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_direct_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_direct --project-id project_a1_ts_cloud_direct --tenant-name "A1 TS Cloud Direct Tenant" --project-name "A1 TS Cloud Direct Project" --dataset-id dataset_a1_ts_cloud_direct --dataset-name "A1 TS Cloud Direct Dataset" --runner-id a1-ts-cloud-direct --run-id run_a1_ts_cloud_direct --max-workers 4 --timeout 5 --fail-on-case-failure`: passed; 30/30 cases passed; trace completeness 1; quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `node packages/ts/ashr-clone/dist/cloud-cli.js run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_cloud_queued_fixture_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_cloud_queued_run_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_queued_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_queued_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_queued --project-id project_a1_ts_cloud_queued --tenant-name "A1 TS Cloud Queued Tenant" --project-name "A1 TS Cloud Queued Project" --dataset-id dataset_a1_ts_cloud_queued --dataset-name "A1 TS Cloud Queued Dataset" --runner-id a1-ts-cloud-queued --run-id run_a1_ts_cloud_queued --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure`: passed; run completed with quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- No hosted Ashr API calls were made. No raw key files were read or copied. Environment-only real API use remains pending.

Known failure points and fixes:

- `apply_patch` wrapper was inaccessible in this PowerShell environment (`Access is denied`) and Git Bash could not resolve the wrapper. Two small text edits were made by exact PowerShell replacements after repeated `apply_patch` failures; this tool issue should be watched in later turns.
- Initial TS expansion tests exposed that sample run fixtures without `ended_at` remain `submitted`; helper was corrected to include `ended_at` for completed local run semantics.
- Initial CLI error path returned code 1 with `ashr-clone-cloud error`; direct cloud CLI now returns code 2 with `cloud api error:` to match Python CLI style.

Next top 10:

1. Add TypeScript schema snapshot validation against `docs/a1/schemas/*.schema.json` and generated fixtures.
2. Add TS hosted injected-transport quota/error fixture pack with response-key and redaction assertions.
3. Add a combined fresh setup smoke script that runs Python 133, TS 133, TS direct 30-case, and TS queued 30-case.
4. Add TS package examples mirroring Python README examples one-for-one.
5. Add TS API client real-call dry-run/small-batch plan path gated only by environment variables.
6. Add media/non-text replay fixtures with image/audio/file/video examples in both Python and TS runner outputs.
7. Add project/tenant quota ledger persistence examples for cloud runtime docs.
8. Add CI-friendly command matrix for A1 owned tests.
9. Add private evidence manifest summarizing generated ignored fixture paths without payload content.
10. Recheck official Ashr dashboard/API docs with Chrome before the next hosted API calibration.
## 2026-07-05 TS Schema Contract and Cross-Runtime Loader

Goal: close the TypeScript/Python schema drift after the full TS parity sprint, so TS-generated run fixtures validate against A1 JSON schemas and load through the Python A1 fixture loader.

Baseline and peer state:

- Repo root: `C:/Users/33516/Documents/Ashr`; branch: `codex/a1-local-sdk-runner`; remote: `3351666087/ashr-codex-factory`; active draft PR: #10.
- Commands run first: `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `git status -sb`; `gh pr list --state all --limit 20`.
- Peer changes/impact: no new peer changes observed after fetch. Current dirty files were A1/TS/schema/evidence only. `docs/evidence/private_refs/`, `.secrets/`, `dist/`, and `node_modules/` stayed ignored and were not staged/read for payload content.

Top 10 and decision:

1. Make TS run fixture schema match Python/A1 `ashr.clone.run.v1`: implemented.
2. Make TS trace event shape match A1 schema fields (`seq`, `phase`, `source`, `tags`, `observation`, `metadata`): implemented.
3. Make TS VM stream shape and stream mapping mirror Python `build_vm_frame`: implemented.
4. Add TS schema contract tests against `docs/a1/schemas`: implemented.
5. Add cross-runtime test proving Python `load_run_fixture()` accepts TS-generated fixtures: implemented.
6. Re-run TS 30-case direct cloud smoke: implemented.
7. Re-run TS 30-case queued cloud smoke: implemented.
8. Add real API small-batch calibration: deferred to next slice; no environment key was consumed here.
9. Add fresh setup one-command matrix: deferred.
10. Add media/non-text replay fixture pack: deferred.

Implemented:

- `packages/ts/ashr-clone/src/trace.ts`: aligned run fixture, trace event, and VM stream validation/build helpers with the A1/Python schema contract.
- `packages/ts/ashr-clone/src/runner.ts`: `buildRunFixture` now emits A1 run fields and builds VM stream frames from the exact same canonical event objects emitted in `events`.
- `packages/ts/ashr-clone/test/schema-contract.test.mjs`: validates TS RunResult, runner fixture, trace fixture, and cloud fixture outputs against A1 schemas; also runs a Python subprocess to load a TS-generated run fixture.
- Updated existing TS tests that still expected the old TS-only `ashr.clone.run_fixture.v1` schema.

Validation:

- `npm test --prefix packages/ts/ashr-clone`: passed, 138 tests, 138 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: passed, 133 passed in 9.31s.
- `node packages/ts/ashr-clone/dist/cloud-cli.js run-agent ... a1_ts_direct_schema_*`: 30/30 cases passed, trace completeness 1, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `node packages/ts/ashr-clone/dist/cloud-cli.js run-agent-queued ... a1_ts_queued_schema_*`: completed queued 30-case run, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `git diff --check`: exit 0; CRLF warnings only.

Failure points and fixes:

- The Python loader initially rejected TS-generated fixtures with `ValueError: vm_stream frames must match trace events`. Fixed by generating TS events once and deriving VM frames from those exact event objects with Python-equivalent stream mapping and JSON-normalized observation data.
- JSON Schema validation alone was insufficient because Python performs semantic replay equality for VM frames; the new test now covers that.

Real API and private evidence:

- Real Ashr API was not called in this schema-contract slice. No `D:/desktop/Ashr_key.txt`, `.secrets`, or raw private refs were read or stored.
- Private smoke outputs stayed under ignored paths: `docs/evidence/private_refs/a1_ts_direct_schema_*_30_smoke.json` and `docs/evidence/private_refs/a1_ts_queued_schema_*_30_smoke.json`.

Bus-Auditor follow-up:

- Bus-Auditor flagged the pre-fix Python loader failure and required TS/Python/diff validation before staging. The final validation above satisfies that ready bar.

Next top 10:

1. Real Ashr API field-map dry-run/small-batch probe from `ASHR_API_KEY` / `ASHR_LABS_API_KEY` environment variables only.
2. TS fresh-setup one-command demo for install/build/test/smoke.
3. Expand TS/Python media fixture replay for text/audio/file/image/video parity.
4. Add hosted injected-transport quota/error fixture pack.
5. Add private evidence manifest summarizing ignored smoke output paths without payload content.
6. Add CI-friendly A1 command matrix.
7. Add TS examples mirroring Python docs one-for-one.
8. Add cloud quota ledger persistence docs.
9. Add `tests/integration` scaffold for A1 integration smokes.
10. Recheck Ashr dashboard/API docs with Chrome before hosted calibration.
## 2026-07-05 Real API Batch Calibration Harness

Goal: move A1 from one-off hosted probes to a reusable env-gated batch calibration loop that can safely use real Ashr API calls, summarize response keys and quota errors, and keep text/image/audio/file/video as first-class modalities.

Baseline and peer state:

- Repo root: `C:/Users/33516/Documents/Ashr`; branch: `codex/a1-local-sdk-runner`; active PR #10 was open, draft, and mergeable after fetch.
- Commands run first: `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `git status -sb`; `gh pr list --state all --limit 20`.
- Peer changes/impact: none observed in A1-owned files. Worktree was clean before this slice.
- Key handling: `ASHR_API_KEY` was read from user-level environment into the current process only. No key file, `.secrets`, or private raw payload was read into logs or committed.

Top 10 and decision:

1. Add env-gated TS batch API calibrator with dry-run/read-only/mutating modes: implemented.
2. Run real read-only small-batch API calibration: implemented.
3. Run a bounded text-only mutating small-batch to observe quota behavior: implemented; blocked by hosted quota, no retry.
4. Keep image/audio/file/video as first-class modality plans without spending media quota yet: implemented.
5. Convert real quota error shape into tests: implemented.
6. Convert historical bool `accepted_inputs` media failure into safer object-shaped request generation: implemented in calibrator.
7. Add modality selector to avoid accidental paid media calls: implemented.
8. Add Python/TS verification after hosted probe: implemented.
9. Update public evidence without raw payloads: implemented.
10. Full non-text paid media batch: deferred until quota is available and text quota path is green.

Implemented:

- `packages/ts/ashr-clone/src/calibrate.ts`: new `ashr-clone-calibrate` CLI. It writes a safe manifest plus per-step private records, enforces dry-run -> `--small-batch` -> optional mutating flow, records response keys/status/attempts/error keys/private paths, supports `--modality text,image,audio,file,video`, and emits object-shaped `accepted_inputs` (`{ enabled: ... }`) for hosted create-request compatibility.
- `packages/ts/ashr-clone/package.json`: added `ashr-clone-calibrate` bin.
- `packages/ts/ashr-clone/test/calibrate.test.mjs`: new dry-run, modality, guardrail, and injected small-batch tests.
- `packages/ts/ashr-clone/test/api-client.test.mjs`: added quota error regression test based on the real hosted `Usage limit exceeded for requests` shape.

Real API evidence:

- Dry-run plans written under `docs/evidence/private_refs/a1_real_*_dry_run_plan.json` and `docs/evidence/private_refs/a1_ts_api_calibration_*_dry_run.json`.
- Real read-only probes succeeded with `status_code=200`, `attempts=1`: `init`, `keep_alive`, `list_agents`, `list_datasets`, `list_requests`, `get_dataset(883)`, `list_runs(dataset=883)`, `get_request(580)`, `get_request(581)`.
- `poll_request(580)` returned a controlled failure record for an already failed media request, giving `response_summary.request_failure` evidence.
- Batch calibrator real read-only manifest: `docs/evidence/private_refs/a1_ts_api_calibration_manifest_real_readonly.json`, status `ok`, 5/5 read steps, estimated calls 7, response keys included `features/tenant/user`, `db/message/status`, `_user/agents/status`, `_user/datasets/next_cursor/status`, and `_user/requests/next_cursor/status`.
- Text-only mutating small-batch manifest: `docs/evidence/private_refs/a1_ts_api_calibration_manifest_real_text_mutating.json`, status `partial`; read steps succeeded and `create_request` was blocked by hosted quota, with exact quota counts kept only in ignored private evidence; response keys `status/message/quota`, status_code `200`, attempts `1`.
- Non-text image/audio/file/video paid mutating calls were not executed in this slice because request quota is exhausted and a prior media request already demonstrated a hosted `_failure` shape.

Validation:

- `npm test --prefix packages/ts/ashr-clone`: 145 tests, 145 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed in 9.97s.
- `git diff --check`: exit 0 with CRLF warnings only.

Known gaps:

- Hosted tenant plan currently reports `free`, and request quota is exhausted at `5/5`, so mutating create-request cannot proceed until quota resets/upgrades.
- Real non-text media generation still needs a quota-available batch after text request creation succeeds.
- `apply_patch` remains unavailable in this PowerShell session, so edits used controlled UTF-8 no-BOM file writes.

Next top 10:

1. When quota is available, run `ashr-clone-calibrate --execute --small-batch --include-mutating --modality text --max-retries 0`, then poll the created request.
2. After text succeeds, run one non-text paid modality at a time (`image`, `audio`, `file`, `video`) with `--allow-paid-media` and capture quota/response keys.
3. Parse hosted quota object into first-class SDK error helpers for Python and TS.
4. Add private evidence manifest index for all real API records without payload content.
5. Add TS fresh-setup command that builds, tests, and runs read-only calibrator dry-run.
6. Add Python parity batch calibrator or wrapper around existing probe APIs.
7. Add A3-facing hosted field-map markdown summarizing real response keys.
8. Add integration tests for calibrator manifest schema.
9. Use Chrome/dashboard to verify visible usage counters against API quota response.
10. Keep widening hosted API coverage: runs, datasets, requests, polling, media failures, and quota ledger.

## A1 round - Python calibrator and public-safe API evidence index (2026-07-05T06:33:05Z)

Goal slice:
- Close the uncommitted public-safe hosted API evidence-index work and expand Python SDK parity with a first-class calibration CLI matching the TS dry-run/small-batch guardrail model.
- Keep A1 scope only: SDK/evidence/tests/docs. No A2 judge semantics or A3 dashboard business changed.

Baseline / peer state:
- pwd: C:/Users/33516/Documents/Ashr.
- Branch: codex/a1-local-sdk-runner; remote origin is https://github.com/3351666087/ashr-codex-factory.
- git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags completed.
- gh pr list --state all --limit 20: A1 PR #10 is merged; A2/A3/G3 peer PRs are merged on origin/main. No peer-owned files touched this round.

Top 10 commercial enhancements considered:
1. Python SDK calibrator CLI mirroring TS dry-run/small-batch/mutating/media guardrails. Score: demo 5, risk 5, contract 2, effort 3, API evidence 5. Implemented.
2. Public-safe real API evidence index from ignored private refs. Score: demo 4, risk 5, contract 1, effort 2, API evidence 5. Implemented.
3. Quota error summarizer as SDK helper. Score: demo 3, risk 5, contract 1, effort 2, API evidence 5. Implemented.
4. Runtime queue lease/heartbeat skeleton. Score: demo 4, risk 4, contract 2, effort 4, API evidence 1. Deferred to next runtime slice.
5. TS evidence-index CLI. Score: demo 3, risk 4, contract 1, effort 3, API evidence 4. Deferred; Python index currently aggregates TS private records.
6. Chrome usage counter verification. Score: demo 3, risk 3, contract 1, effort 3, API evidence 3. Deferred.
7. Mutating text real probe. Score: demo 5, risk 4, contract 1, effort 1, API evidence 5. Deferred this round because prior hosted quota block remains documented; no purposeless retry.
8. Non-text paid media probes. Score: demo 5, risk 4, contract 2, effort 3, API evidence 5. Deferred until request quota is available.
9. JSON schema for evidence index artifact. Score: demo 3, risk 4, contract 1, effort 2, API evidence 3. Deferred.
10. One-command A1 readiness matrix. Score: demo 4, risk 4, contract 1, effort 3, API evidence 2. Deferred.

Implemented:
- Added packages/sdk/ashr_clone/calibrate.py: Python module CLI with dry-run default, execute/small-batch/max-retries-zero guardrail, mutating opt-in, explicit paid media opt-in, text/image/audio/file/video request plans, private step records, and safe manifest summary.
- Added packages/sdk/ashr_clone/evidence.py: public-safe index builder for ignored private API evidence records.
- Added summarize_quota_error() in packages/sdk/ashr_clone/api_client.py and root export in packages/sdk/ashr_clone/__init__.py.
- Added tests tests/a1/test_python_calibrator.py and tests/a1/test_evidence_index.py.
- Regenerated docs/a1/api_calibration/real_api_evidence_index.json from a1_real_*, a1_ts_api_calibration_*, and a1_python_api_calibration_* private records.

Official API calibration:
- Key source: environment variable presence only. No raw key printed or written.
- Dry-run plan: python -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_dry_run.json --print-record.
  - Result: planned, 10 steps, 5 read + 5 mutating plans, modalities audio/file/image/text/video, estimated calls 17.
- Real read-only small batch: python -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real_readonly.json --print-record.
  - Result: ok, 5/5 read steps, status_code 200, attempts 1 each.
  - Response key coverage: init -> features/notes/status/tenant/user; keep_alive -> db/message/status; list_agents -> _user/agents/status; list_datasets -> _user/datasets/next_cursor/status; list_requests -> _user/next_cursor/requests/status.
- Public evidence index: docs/a1/api_calibration/real_api_evidence_index.json now reports 61 records, status counts error=4, failed=1, ok=28, partial=1, planned=26, quota block count 1.
- Mutating hosted calls were not repeated because the prior controlled text create-request probe already captured a hosted request quota block; exact counts remain only in ignored private evidence, and avoiding no-purpose quota retries matches the API rule.

Validation:
- python -B -m pytest tests/a1 -q -p no:cacheprovider: 144 passed.
- npm test --prefix packages/ts/ashr-clone: 145 passed.
- git diff --check: exit 0 with CRLF warnings only for packages/sdk/ashr_clone/api_client.py.

Bus-Auditor / reviewer feedback:
- Commit current evidence-index slice after full tests: followed.
- Fix error_kind_counts top-level counting bug: fixed and regenerated public index.
- Next likely high-ROI slice: A1 runtime queue lease/heartbeat skeleton or TS public evidence-index CLI.

Known gaps:
- Request quota remains exhausted on hosted plan, so mutating text/media real probes need quota reset/upgrade before useful paid calibration.
- Python calibrator is module-invoked rather than installed console-script because current Python SDK has no packaging entrypoint.
- TS still lacks its own standalone evidence-index command, though the Python public index aggregates TS calibration records.

Next top 10:
1. Add runtime queue lease/heartbeat fields and reclaim tests for services/api/services/runner.
2. Add TS evidence-index CLI/schema tests mirroring Python indexer.
3. Add A1 readiness command/script covering Python tests, TS tests, evidence scan, diff check.
4. Add JSON schema for ashr.clone.evidence_index.v1.
5. Re-run text mutating real calibration when quota is available.
6. Then run image/audio/file/video paid media probes one modality at a time.
7. Chrome/dashboard usage counter verification against API quota response.
8. Add hosted response-key field map markdown generated from evidence index.
9. Add Python console script packaging if/when SDK packaging lands.
10. Add public-safe private evidence freshness checker for stale/failed calibration files.

## A1 round - queue lease runtime and TS evidence parity (2026-07-05T17:20:07Z)

Goal slice:
- Move A1 cloud runtime closer to commercial queue behavior by adding persisted run leases, heartbeat renewal, expired-lease reclaim, and owner-validated completion/failure.
- Add TypeScript public-safe evidence-index parity with the Python SDK helper.
- Continue real Ashr API calibration with bounded read-only and missing-resource probes using ASHR_API_KEY from environment only.

Baseline / peer state:
- Repo root: C:/Users/33516/Documents/Ashr; branch: codex/a1-local-sdk-runner; PR #11 is open draft and clean.
- git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags completed.
- Peer changes: origin/main and origin/dev/g3-a2-calibration have newer A2/G3 evidence/readiness work; no peer-owned files changed in this slice.
- Untracked output/ and tmp/ remain present and intentionally unstaged.

Top 10 commercial enhancements considered:
1. Queue lease/heartbeat/reclaim runtime. Scores: demo 5, risk 5, contract 2, effort 4, API evidence 1. Implemented.
2. TS evidence-index parity. Scores: demo 3, risk 4, contract 1, effort 2, API evidence 4. Implemented.
3. Real API read-only and missing-resource calibration matrix. Scores: demo 4, risk 4, contract 1, effort 2, API evidence 5. Implemented.
4. One-command A1 readiness matrix. Scores: demo 4, risk 4, contract 1, effort 3, API evidence 2. Deferred.
5. Evidence-index JSON schema. Scores: demo 3, risk 4, contract 1, effort 2, API evidence 3. Deferred.
6. Chrome dashboard usage counter verification. Scores: demo 3, risk 3, contract 1, effort 3, API evidence 3. Deferred.
7. Mutating text create_request retry. Scores: demo 5, risk 4, contract 1, effort 1, API evidence 5. Deferred because prior quota block is already captured and no-purpose retry would burn failure calls.
8. Non-text paid media probes. Scores: demo 5, risk 4, contract 2, effort 3, API evidence 5. Deferred until request quota is available.
9. Python package console script. Scores: demo 3, risk 2, contract 1, effort 3, API evidence 1. Deferred.
10. Ignore generated output/tmp. Scores: demo 2, risk 4, contract 1, effort 1, API evidence 0. Deferred to avoid mixing housekeeping with runtime slice.

Implemented:
- services/api/runtime.py: queued run lease fields, mark_run_running lease acquisition, heartbeat_run, reclaim_expired_run_leases, owner validation, terminal lease clearing, and permanent-lease guard.
- services/api/queue_worker.py: worker leases queued/replayed runs, periodically renews active leases during long run_agent_batch execution, skips actively leased runs, reclaims expired leases before replay, and returns current run state on stale-owner failure paths.
- tests/a1/test_cloud_api.py: lease owner validation, permanent lease rejection, active lease no-double-replay with slow agent, expired running lease reclaim/replay, and status-history assertions.
- packages/ts/ashr-clone/src/evidence.ts plus index export and tests: TS public-safe evidence-index helper matching Python summary shape.
- docs/a1/api_calibration/real_api_evidence_index.json regenerated from private real/TS/Python calibration records and round2 missing-resource probes.

Real API calibration:
- Env: ASHR_API_KEY present in process; raw key not printed or committed.
- Dry-run: python -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round2_dry_run.json.
  - Result: planned, 10 steps, five modalities, estimated calls 17.
- Real read-only: python -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round2_real_readonly.json.
  - Result: ok, 5 read steps, no errors.
- Missing-resource probes: get_dataset(999999) and get_request(999999) with max_retries=0.
  - Results: controlled API errors Dataset not found and Request not found; private evidence under docs/evidence/private_refs/a1_python_api_get_dataset_999999_round2_real.json and docs/evidence/private_refs/a1_python_api_get_request_999999_round2_real.json.
- Public index now reports 67 records, status counts error=8/failed=1/ok=29/partial=1/planned=27, error_kind_counts api=7, quota_block_count=1.

Validation:
- python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider: 35 passed.
- python -B -m pytest tests/a1 -q -p no:cacheprovider: 148 passed.
- npm test --prefix packages/ts/ashr-clone: 147 passed.
- git diff --check: exit 0 with CRLF warnings only.

Bus/Review feedback:
- Bus-Auditor approved the runtime lease slice but warned not to stage output/ or tmp/: followed.
- Reviewer found P1 active-run double execution risk with non-periodic heartbeat: fixed with active lease renewer and slow-agent test.
- Reviewer found stale-owner exception masking risk: fixed by polling current run state if fail_run is rejected by lease owner validation.
- Reviewer found lease_seconds=None could create unreclaimable leased runs: fixed by rejecting owner claims without a finite positive lease.

Known gaps:
- Runtime lease behavior is implemented in Python cloud runtime; TS runtime lease parity is still a follow-up.
- Hosted request quota still blocks useful mutating create_request calibration; media paid probes remain deferred until quota is available.
- output/ and tmp/ should be ignored or cleaned in a separate housekeeping slice.

Next top 10:
1. Add TS cloud queue lease/heartbeat parity and tests.
2. Add one-command A1 readiness matrix script.
3. Add JSON schema for ashr.clone.evidence_index.v1 and validate Python/TS outputs.
4. Add public-safe hosted field-map markdown generated from evidence index.
5. Chrome/dashboard usage counter verification against API quota evidence.
6. Re-run one text mutating probe when quota resets or plan upgrades.
7. Then run image/audio/file/video paid probes one modality at a time.
8. Add evidence freshness checker for stale private refs and failed calibration manifests.
9. Add CLI flags for Python calibrator missing-resource boundary probes.
10. Housekeep generated output/ and tmp/ ignore rules in a dedicated non-runtime slice.

## A1 round - TS/Python queue lease parity hardening and readiness matrix (2026-07-06T11:45:00Z)

Goal slice:
- Harden TS cloud queue lease parity until it matches Python queue worker failure semantics closely enough for commercial batch replay.
- Add a one-command A1 readiness matrix, public-safe evidence-index schema validation without undeclared dependencies, and explicit cloud API lease schema fields.
- Continue real Ashr API calibration with env-only read-only probes; no mutating calls while the prior hosted request quota block remains documented.

Baseline / peer state:
- Repo root: `C:/Users/33516/Documents/Ashr`; branch: `codex/a1-local-sdk-runner`; PR #11 remains open draft.
- Required start commands were run: `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `git status -sb`; `gh pr list --state all --limit 20`.
- Peer changes: `origin/dev/g3-a2-calibration` advanced to `bf5028a A2: add external preflight schema`. It changes A2 docs/fixtures/judge/report paths and A1-adjacent Python calibrator/evidence tests. These were read-only reviewed and not merged into this A1 commit.
- Local generated `tmp/` and `output/` are non-A1 artifacts; they were added to local `.git/info/exclude` only and are not part of the commit.

Top 10 commercial enhancements considered:
1. TS queue lease correctness parity: unique worker owners, active-future cleanup, stale-owner protection, heartbeat guardrails. Scores: demo 5, risk 5, contract 2, effort 3, API evidence 1. Implemented.
2. Python queue lease hardening to match the stricter TS contract. Scores: demo 4, risk 5, contract 2, effort 2, API evidence 1. Implemented.
3. A1 readiness matrix script with optional real read-only calibration. Scores: demo 5, risk 4, contract 1, effort 3, API evidence 4. Implemented.
4. Evidence-index JSON schema and dependency-free public validation. Scores: demo 3, risk 4, contract 1, effort 2, API evidence 4. Implemented.
5. Explicit cloud API schema fields for run leases. Scores: demo 3, risk 4, contract 2, effort 1, API evidence 1. Implemented.
6. Real Python and TS read-only calibration refresh from env key. Scores: demo 4, risk 4, contract 1, effort 2, API evidence 5. Implemented.
7. Chrome docs/dashboard usage recheck. Scores: demo 3, risk 3, contract 1, effort 2, API evidence 3. Implemented as safe summary; Usage counters were not reliably extracted.
8. Python calibrator request shape merge with A2 peer branch. Scores: demo 4, risk 4, contract 1, effort 3, API evidence 4. Deferred to avoid mixing peer branch changes into TS lease commit.
9. Mutating text probe retry. Scores: demo 5, risk 3, contract 1, effort 1, API evidence 5. Deferred because quota block is already captured and no reset was proven.
10. Paid image/audio/file/video probes. Scores: demo 5, risk 4, contract 2, effort 3, API evidence 5. Deferred until a useful text create_request path is quota-available.

Implemented:
- `packages/ts/ashr-clone/src/cloud-queue.ts`: worker owners are now instance-unique, settled futures are removed so requeued/reclaimed runs can replay, execution metadata records the generated owner, wait timeout polls current run state before failing, and stale worker errors fall back to polling current state.
- `packages/ts/ashr-clone/src/index.ts`: `heartbeatRun` rejects `leaseSeconds: null`; leased runs require matching `leaseOwnerId` for `completeRun` / `failRun`; `completeRun` rejects non-terminal completion payloads instead of clearing a lease on `queued`/`running`.
- `services/api/runtime.py`: mirrors the heartbeat-null, leased terminal-write, and terminal completion guardrails in Python cloud runtime.
- `packages/ts/ashr-clone/test/cloud-queue.test.mjs` and `tests/a1/test_cloud_api.py`: added stale owner, active lease, settled future, heartbeat-null, no-owner terminal write, and terminal-status tests.
- `docs/a1/schemas/cloud_api.schema.json`: explicitly documents `lease_owner_id`, `lease_expires_at`, `lease_heartbeat_at`, and `lease_reclaim_count`.
- `docs/a1/schemas/evidence_index.schema.json` plus `tests/a1/test_evidence_index.py`: public evidence index shape is validated without adding an undeclared `jsonschema` dependency.
- `tests/integration/a1_readiness.py`: fresh setup matrix for Python A1 tests, TS tests, calibrator dry-run, optional real read-only calibrator, public evidence safety, and `git diff --check`.
- `docs/a1/explorer_chrome.md`: appended the 2026-07-06 read-only Chrome docs/usage check.
- `docs/a1/api_calibration/real_api_evidence_index.json`: refreshed to label `a1-real-api-2026-07-06-round4`, 71 records, quota block count 1.

Subagent and audit feedback:
- Bus-Auditor required handling `tmp/`/`output/`, removing undeclared `jsonschema` dependency, adding cloud API lease schema fields, and staging only A1-owned files. Followed.
- Worker-TS and Worker-Runtime both found P1 stale-owner and settled-future risks in TS queue leases. Fixed and covered with tests.
- Explorer-SDK/API found Python calibrator request-shape drift relative to A2 peer branch. Deferred as next-round SDK/API work because it overlaps peer changes.
- Explorer-Chrome confirmed public docs and plans were reachable and dashboard Usage page was logged in. Main-thread Chrome recheck found public Python/TS API reference fields; Usage page only yielded a reliable `Usage` signal in automated extraction, so no counter values were recorded.
- Reviewer subagent errored with an external `403 Forbidden` image-generation capability issue and produced no review findings; main thread used Bus/TS/Runtime feedback instead.

Real API calibration:
- Env presence: `ASHR_API_KEY_present=True`, `ASHR_LABS_API_KEY_present=False`; raw key was not printed, copied, or stored.
- `python -B tests/integration/a1_readiness.py --real-readonly --summary-output docs/evidence/private_refs/a1_readiness_round4_real_readonly.json`: passed. It ran Python tests, TS tests, calibrator dry-run, real read-only Python calibrator, public evidence safety, and diff check.
- `node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_round4_real_readonly.json`: passed with `status=ok`, 5 read steps, 0 errors, estimated calls 7.
- Private evidence paths: `docs/evidence/private_refs/a1_readiness_round4_real_readonly.json`, `docs/evidence/private_refs/a1_readiness_calibration_real_readonly.json`, `docs/evidence/private_refs/a1_readiness_calibration_dry_run.json`, `docs/evidence/private_refs/a1_ts_api_calibration_manifest_round4_real_readonly.json`, and `docs/evidence/private_refs/a1_readiness_final_safety.json`.
- No mutating call was executed this round; prior request quota block remains documented in ignored private evidence.

Validation:
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 149 passed.
- `npm test --prefix packages/ts/ashr-clone`: 152 passed.
- `python -B tests/integration/a1_readiness.py --real-readonly --summary-output docs/evidence/private_refs/a1_readiness_round4_real_readonly.json`: status ok, 6 steps.
- `node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_round4_real_readonly.json`: status ok.
- `python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider`: 4 passed.
- `python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_final_safety.json`: status ok, 2 steps.
- `git diff --check`: exit 0 with CRLF warnings only.
- Failed command noted: one bash heredoc-style Python inspection command failed in PowerShell; rerun with a PowerShell-compatible `python -B -c` command succeeded.

Known gaps:
- Python calibrator request shape should be reconciled with A2 peer's `agent.accepted_inputs` change before the next Gate.
- TS queue parity is strong for async/IO agent behavior; CPU-blocking synchronous JS agents can still block heartbeat because Node runs them on the event loop.
- Dashboard Usage counter values were not reliably extracted in the main-thread Chrome pass; keep exact counter values private if captured later.
- Mutating text/media probes remain blocked until quota reset/plan state is proven useful.

Next top 10:
1. Merge or reimplement the A2 peer-compatible Python calibrator request shape (`agent.accepted_inputs`, `output_format`, generation flags) in A1 branch.
2. Add Python SDK direct `create_request` preflight helpers matching TS guardrails.
3. Extend Python/TS calibrators with optional ID-driven `get_dataset`, `list_runs`, `get_request`, `poll_request`, and `create_run` matrix.
4. Generate a public hosted field-map markdown from the 71-record evidence index.
5. Add TS evidence-index CLI parity so TS can generate public-safe indexes without Python.
6. Add queue lease docs for async JS heartbeat boundary and CPU-blocking agent caveat.
7. Run a single text mutating probe after quota reset/upgrade is visible, then poll the created request.
8. Run image/audio/file/video paid probes one modality at a time only after text mutating succeeds.
9. Chrome/dashboard usage counter verification with private screenshot and no API key page access.
10. Add CI-friendly A1 readiness command to docs/a1 README and PR description.

## A1 round - Python SDK preflight enforcement, official shape parity, and round5 API calibration (2026-07-06T21:35:00+08:00)

Goal slice:
- Close the P1 gap where direct Python SDK `create_request` could bypass media/non-text/variation preflight rules that only existed in `services.runner.api_probe`.
- Re-align Python calibrator request shape with TS and observed public docs: `agent.accepted_inputs`, `agent.tools`, `agent.output_format`, and `generation_options.generate_*`.
- Use official docs/dashboard boundary evidence and real Ashr API small-batch calibration from environment-only auth, without storing or printing raw keys.

Baseline / peer state:
- Repo root: `C:/Users/33516/Documents/Ashr`; branch: `codex/a1-local-sdk-runner`; PR #11 remains open draft.
- Required start commands run: `pwd`, `git rev-parse --show-toplevel`, `git remote -v`, `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`, `git status -sb --untracked-files=all`, `gh repo view`, and `gh pr list --state all`.
- Peer changes reviewed: `origin/dev/g3-a2-calibration` had the correct nested Python calibrator request shape; only the needed A1-owned shape logic was reimplemented, no A2/A3 judge/dashboard files were touched.
- Chrome/official check: Explorer-Chrome appended a read-only public docs and dashboard boundary note to `docs/a1/explorer_chrome.md`. API Keys, checkout, payment, and credential pages were not opened.

Top 20 A1 growth points considered this round:
1. SDK-level direct `create_request` preflight enforcement for real paid mutations. Implemented.
2. Python `summarize_generation_request` helper parity with TS `summarizeGenerationRequest`. Implemented.
3. Python `enforce_create_request_preflight` helper parity with TS `enforceCreateRequestPreflight`. Implemented.
4. Runner `api_probe` reuse of SDK helpers to prevent drift. Implemented.
5. Python calibrator nested `agent.accepted_inputs` request shape. Implemented.
6. Python calibrator generation flags for image/audio/file/video/simulation. Implemented.
7. Default `request_input_schema_source` tracking for client-default vs explicit schema. Implemented.
8. Direct SDK tests proving unsafe real calls block before transport/session. Implemented.
9. Dry-run calibrator evidence for all five modalities. Implemented.
10. Real read-only Python calibration refresh. Implemented.
11. Controlled text-only mutating calibration to refresh current quota/error shape. Implemented; quota blocked.
12. Public-safe evidence index refresh from private refs. Implemented.
13. Official docs parity note for Python/TS `create_request` and `accepted_inputs`. Implemented by Explorer-Chrome.
14. Dashboard Usage boundary note for Images/Audio/Files counters. Implemented as a gap; authenticated counter table did not load.
15. A1 readiness safety smoke after evidence refresh. Implemented.
16. A1 secret scan over touched public files. Implemented; only synthetic test tokens matched.
17. Redact exact hosted quota counts in public evidence while keeping private evidence detailed. Implemented after Growth-Auditor review.
18. Real media mutating calibration for image/audio/file/video. Deferred because text create-request is still request-quota blocked.
19. Broader create-run/list-runs/poll-run hosted lifecycle calibration. Deferred to next A1 growth round.
20. Production trace ingestion / old-vs-new diff / self-host worker growth. Deferred to next round after current SDK/API safety commit.

Implemented:
- `packages/sdk/ashr_clone/api_client.py`: added SDK-owned `summarize_generation_request`, `enforce_create_request_preflight`, max-variation coercion, accepted input shape parsing, and direct `create_request` guardrails before session/network on real execution.
- `packages/sdk/ashr_clone/__init__.py`: exported the new Python SDK preflight helpers.
- `services/runner/api_probe.py`: removed local duplicate preflight implementation and now reuses SDK helpers; CLI forwards allow flags into `AshrApiClient.create_request`.
- `packages/sdk/ashr_clone/calibrate.py`: emits TS/public-doc-compatible request bodies with nested `agent.accepted_inputs`, `agent.output_format`, `agent.tools`, `test_config.num_variations`, and `generation_options.generate_audio/files/images/videos/simulations`; no top-level `agent_input_parts`.
- `packages/sdk/ashr_clone/evidence.py`: public-safe evidence index now redacts exact quota counts into `*_present` booleans while private refs retain full detail.
- `docs/a1/schemas/evidence_index.schema.json`: quota schema now documents public-safe presence booleans.
- `tests/a1/test_api_client.py`: added direct SDK guardrail tests for unknown variations, media generation, non-text inputs, variation count limits, and explicit allow flags.
- `tests/a1/test_python_calibrator.py`: updated calibrator request-shape assertions for nested agent fields and media generation flags.
- `tests/a1/test_evidence_index.py`: verifies public evidence index quota summaries do not expose exact hosted quota counts.
- `docs/a1/api_calibration/real_api_evidence_index.json`: refreshed public-safe index to round5.
- `docs/a1/explorer_chrome.md`: appended official docs/plans/dashboard boundary evidence from Chrome.
- `docs/a1/evidence/commands.md`: appended command/evidence ledger for this round and redacted exact quota counts from tracked text.

Real API calibration:
- Key source: process environment only. Raw `ASHR_API_KEY` / `ASHR_LABS_API_KEY` value was not printed, copied, stored, or committed.
- Dry-run plan: `python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_dry_run.json`.
  - Result: planned, 10 steps, 5 read + 5 mutating plans, modalities audio/file/image/text/video, estimated calls 17.
- Real read-only: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_real_readonly.json`.
  - Result: ok, 5/5 read steps, estimated calls 7, no errors.
- Controlled real text mutation: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --include-mutating --modality text --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_real_text_mutation.json`.
  - Result: partial, read steps ok, `create-request-text` returned a hosted quota block. Exact quota counts remain only in ignored private evidence. No retry and no media mutation was run.
- Public evidence index: 75 records, status counts `error=9`, `failed=1`, `ok=33`, `partial=2`, `planned=29`, quota block count 2.

Validation:
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_python_calibrator.py -q -p no:cacheprovider`: 60 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 154 passed.
- `npm test --prefix packages/ts/ashr-clone`: 152 passed.
- `python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider`: 4 passed after quota-redaction change.
- `python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round5_final_safety.json`: status ok, 2 steps.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret scan over touched public files matched only intentional synthetic test strings such as `tp_test_secret`; no real key material observed.
- Failed command noted: one PowerShell `python -c` inspection command used literal `\n` and failed with SyntaxError; rerun with a PowerShell-compatible one-liner succeeded.

Growth-Auditor feedback:
- Verdict: real commercial-grade hardening step, not toy work.
- P0: none found.
- P1 accepted/fixed before commit: public evidence/logs contained exact quota counts. Fixed by redacting public evidence quota counts into presence booleans and tracked-log wording while preserving full private evidence.
- Remaining P1 risk: quota exhaustion means round5 does not prove successful real Python `create_request` after the shape/preflight fix. This is recorded as a hosted quota blocker, not a local code blocker.

Known gaps:
- Hosted request quota remains exhausted for `create_request`, so media/non-text paid real probes cannot produce useful creation evidence yet.
- Dashboard Usage authenticated counter values for Images/Audio/Files did not load; only safe public/onboarding labels were recorded.
- A2 peer review-status/redaction compatibility remains outside A1-owned changes, but should be coordinated before a Gate that consumes A2 calibration evidence.
- Real run lifecycle expansion (`create_run`, `list_runs`, `poll_run`) still needs a dedicated A1 round with safe dataset/run IDs.

Next top 20:
1. Add hosted lifecycle calibration matrix for `list_runs`, `get_run`, `create_run` dry-run/safe real boundaries.
2. Add request quota reset detector and stop/go gate before any media mutating calibration.
3. Add media mutating calibration queue that runs text first, then image/audio/file/video one-by-one only when quota is available.
4. Add public field-map markdown generated from the 75-record evidence index.
5. Add Python/TS parity test that compares preflight helper outputs on shared fixtures.
6. Add A1 CLI command for `create_request` preflight explain output for customer review workflows.
7. Add production trace ingestion schema for external OpenAI-style traces.
8. Add deterministic old-vs-new replay diff fixture and tests.
9. Add self-host worker heartbeat/lease docs plus CPU-blocking JS caveat.
10. Add enterprise audit manifest tying commands, code diff, tests, and private evidence refs.
11. Add per-tenant/project quota ledger export/import for offline enterprise audits.
12. Add official docs drift checker for Python/TS API reference fields.
13. Add dashboard Usage screenshot evidence flow that redacts counters by default but records field labels.
14. Add request/run replay package for A3 with three fresh round5 fixtures.
15. Add API client typed exceptions for quota vs validation vs hosted failure.
16. Add public-safe private evidence freshness checker for stale calibration records.
17. Add batch-run fixture generator at 80 cases with max_workers >= 8 stress coverage.
18. Add TS CLI parity for Python calibrator shape/schema assertions.
19. Add schema contract tests for media/non-text safe envelope across Python, TS, and cloud runtime.
20. Coordinate A2/A3 Gate-only contract change request for any shared review-status or evidence metadata.
