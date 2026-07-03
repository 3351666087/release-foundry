# A2 Scenario Coverage Plan

Final A2 target:

- 60 scenarios
- 5 rubric classes
- 5 judge modes
- 20 golden cases
- 12 failure classes

## Rubric Classes

1. `task_completion`
2. `skill_protocol`
3. `argument_fidelity`
4. `safety_permissions`
5. `final_response_quality`

## Judge Modes

G1-G2 deterministic local modes:

1. `g1_trace_contract_judge`
2. `g2_output_contract_judge`

Later calibration modes:

3. `g3_semantic_reference_judge`
4. `g3_replay_sandbox_judge`
5. `g4_panel_adjudication_judge`

## 60-Scenario Families

| Family | Count | Purpose |
|---|---:|---|
| `direct_answer` | 10 | No-tool answers, formatting, concise edits |
| `retrieval_grounding` | 10 | File/web/resource grounding and citation discipline |
| `tool_execution` | 10 | Required tool calls, arguments, current information |
| `workflow_planning` | 10 | Multi-step order, retries, recovery, state deltas |
| `safety_policy` | 10 | Forbidden tools, privacy, unsafe requests, boundaries |
| `ambiguous_or_conflicting` | 10 | Clarification, conflicting turns, multi-turn memory |

## G2 Seed Pack

The first 20 scenarios live in `packages/scenarios/a2_g2_seed_pack.json`. They cover all core policy shapes:

- no tool
- optional tool
- required single tool
- required ordered tools
- forbidden tool
- missing information clarification
- ambiguous intent
- tool error retry
- wrong arguments
- ignored tool result
- multi-turn memory
- unsafe request
- recovery after refusal

## Later Enhancements

Community metadata such as GitHub stars, issue activity, adoption, and documentation quality can become later metadata signals. They should not affect G1-G2 deterministic scores.
