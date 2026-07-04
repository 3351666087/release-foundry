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

G3 deterministic local modes:

1. `g1_trace_contract_judge`
2. `g2_output_contract_judge`
3. `g3_replay_sandbox_judge`
4. `g3_semantic_reference_judge`
5. `g3_safety_boundary_judge`

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

## G3 Full Pack

The full 60-scenario pack lives in `packages/scenarios/a2_g3_full_pack.json`.

It keeps 10 scenarios per family and is the default pack for `services.judge.runner.grade_run`.

G3 also adds:

- 5 active deterministic judge modes,
- A2 aggregate grade report fixture at `fixtures/a2/results/a2_g3_grade_results.json`,
- A2-S010 wrong-arguments real output fixture for A3 failure clustering,
- coverage reporting via `services.judge.coverage.build_coverage_report`.

Each G3 scenario also has coverage-audit metadata:

- `primaryRubric`: one of the 5 rubric classes. The 60-pack assigns exactly 12 primary scenarios to each rubric class.
- `primaryFailureClass`: one of the 12 canonical failure classes. The 60-pack covers every canonical class at least once.

These fields make coverage auditable; runtime judges still grade actual run behavior.

The coverage report also reads `fixtures/golden/a2_g2_golden_cases.json` and reports:

- `golden_case_count`: expected to stay at 20 or higher,
- `golden_pass_case_count`,
- `golden_failure_case_count`: expected to stay at 12 or higher,
- `golden_failure_class_counts`: canonical expected failure distribution for calibration seeds.

## Later Enhancements

Community metadata such as GitHub stars, issue activity, adoption, and documentation quality can become later metadata signals. They should not affect G1-G2 deterministic scores.
