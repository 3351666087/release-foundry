# Reviewer Notes

Resolved: facade exports `build_vm_stream`; adapter exposes `AgentResult`, `respond`, `arespond`, history, reset state, and `run_turn` aliases; runner emits A3-oriented `RunResult` with observations, grade, agent output, VM metadata, and trace completeness.

Remaining: A2 final `Scenario` / Judge / Golden adapters should wait for Gate contract.
