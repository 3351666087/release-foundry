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
