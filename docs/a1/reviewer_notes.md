# Reviewer Notes

Resolved: facade exports `build_vm_stream` plus A3 fixture helpers; adapter exposes `AgentResult`, `respond`, `arespond`, history, reset state, and `run_turn` aliases; runner emits A3-oriented `RunResult` with observations, grade, agent output, VM metadata, and trace completeness.

Follow-up resolved: `run_agent_batch` now builds a per-case agent from class/string/clone/deepcopy when possible and serializes only non-cloneable shared instances with a lock. Tests cover stateful existing-agent instances, deepcopy fallback, shared-lock fallback, agent-mode mixed pass/fail/error/timeout accounting, CLI nonzero failure behavior for generic and agent paths, committed fixture loading, and top-level A3 helper imports.

Adapter follow-up resolved: non-callable `respond` attributes no longer mask callable agents; sync `respond/reset` can wrap async agents even when called inside an existing event loop; `AgentResult.to_dict()` now returns JSON-safe data. Timeout remains a Runner-level contract because Python cannot safely cancel arbitrary external sync agent code.

Round 3 resolved: agent timeout/error cases now emit A3-consumable failure traces with user + system observations, synthetic VM stream metadata, and `grade.actual.error`; VM stream frames are strictly validated against trace events; `AgentTurn` output includes `schema_version: ashr.clone.agent_turn.v1`; local schema snapshots live in `docs/a1/schemas`.

Round 4 resolved: negative default `timeout_seconds` / CLI `--timeout` values are rejected before execution, and negative per-case timeout values become schema-safe A3 error cases instead of negative latency/duration payloads. Tests now cover CLI rejection, case-level negative timeout handling, and an emitted mixed RunResult schema guard for required fields and minimum-zero timing fields.

Round 5 resolved: A2 peer handoff expects `final_response` and `tool_calls[].tool` / `tool_calls[].args`; A1 now exposes `to_a2_judge_run(...)` to project local `AgentTurn` / `agent_output` into that shape without modifying A2 judge semantics or Gate contracts.

Remaining: A2 final `Scenario` / Judge / Golden adapters should wait for Gate contract.
