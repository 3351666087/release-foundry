# Reviewer Notes

Resolved: facade exports `build_vm_stream` plus A3 fixture helpers; adapter exposes `AgentResult`, `respond`, `arespond`, history, reset state, and `run_turn` aliases; runner emits A3-oriented `RunResult` with observations, grade, agent output, VM metadata, and trace completeness.

Follow-up resolved: `run_agent_batch` now builds a per-case agent from class/string/clone/deepcopy when possible and serializes only non-cloneable shared instances with a lock. Tests cover stateful existing-agent instances, deepcopy fallback, shared-lock fallback, agent-mode mixed pass/fail/error/timeout accounting, CLI nonzero failure behavior for generic and agent paths, committed fixture loading, and top-level A3 helper imports.

Adapter follow-up resolved: non-callable `respond` attributes no longer mask callable agents; sync `respond/reset` can wrap async agents even when called inside an existing event loop; `AgentResult.to_dict()` now returns JSON-safe data. Timeout remains a Runner-level contract because Python cannot safely cancel arbitrary external sync agent code.

Remaining: A2 final `Scenario` / Judge / Golden adapters should wait for Gate contract.
