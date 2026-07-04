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
