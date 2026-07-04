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
- executable A2 run fixtures covering all 12 canonical failure classes plus one passing baseline,
- coverage reporting via `services.judge.coverage.build_coverage_report`,
- saved coverage audit fixture at `fixtures/a2/results/a2_g3_coverage_report.json`.

Each G3 scenario also has coverage-audit metadata:

- `primaryRubric`: one of the 5 rubric classes. The 60-pack assigns exactly 12 primary scenarios to each rubric class.
- `primaryFailureClass`: one of the 12 canonical failure classes. The 60-pack covers every canonical class at least once.

These fields make coverage auditable; runtime judges still grade actual run behavior.

The coverage report also reads `fixtures/golden/a2_g2_golden_cases.json` and reports:

- `golden_case_count`: expected to stay at 20 or higher. The first 20 cases cover the 20 G2 seed scenarios; extra cases may be added as failure calibration seeds.
- `golden_pass_case_count`,
- `golden_failure_case_count`: expected to stay at 12 or higher,
- `golden_failure_class_counts`: canonical expected failure distribution for calibration seeds,
- `golden_failure_classes_missing`: expected to stay empty after G3 calibration.

The golden set now contains at least two calibration cases for every canonical failure class, so `thin_golden_failure_classes` is expected to stay empty.

It also audits executable run fixtures in `fixtures/a2/runs`:

- `executable_run_case_count`,
- `executable_failure_case_count`: expected to stay at 12 or higher,
- `executable_failure_class_counts`,
- `executable_failure_classes_missing`: expected to stay empty after executable G3 calibration.

G3 executable calibration now includes seed and non-seed tool/workflow scenarios for shell inspection, image inspection, media API pipelines, MCP resource lookup, calculator argument fidelity, and retry/failure recovery. These fixtures make more of the 60-pack auditable through actual runner output rather than metadata alone.

The executable workflow calibration also includes ordered-tool checks for cross-tool flows (`web.search` before `web.open`), same-tool argument-aware flows (`file.read` Q1 before `file.read` Q2), and media API flows (`media.fetch` before `image.view` before `media.classify`).

Media API calibration also checks tool-output grounding. A2-S031 uses `expectedToolOutputFacts` so a final answer must be supported by the `media.classify` output, not only by the final response text.

Authenticated G3 calibration is optional and separate from deterministic unit tests. `scripts/a2_real_api_smoke.py` uses `ASHR_LABS_API_KEY` from the environment, performs read/list API calls, and writes only a redacted summary to `docs/evidence/a2_real_api_smoke.json`.

The G3 coverage report also includes `assignment_minimums`, `assignment_checks`, `meets_assignment_minimums`, and calibration redundancy warnings. Thin coverage is not a failing condition by itself; it marks failure classes that only have the minimum calibration depth and should be prioritized in later iterations.

After the G3 calibration pass, both `thin_golden_failure_classes` and `thin_executable_failure_classes` are expected to stay empty, meaning every canonical failure class has at least two golden cases and at least two executable run fixtures.

For auditability, the coverage report also exposes `golden_failure_class_cases` and `executable_failure_class_cases`, which list the case/scenario evidence behind each canonical failure class count.

G3 now also audits scenario quality dimensions beyond the assignment minimums:

- `scenario_dimension_counts`, `scenario_dimension_checks`, and `scenario_dimension_scenarios` show coverage for task shapes such as required tool use, optional tool choice, forbidden-tool boundaries, ordered tool sequences, multi-turn dialogue, fixture grounding, clarification, failure recovery, safety, grounding/reference, argument fidelity, output contracts, freshness/current-info, and tool-output grounding.
- `difficulty_counts`, `action_count_counts`, `environment_counts`, `tag_counts`, `tool_policy_shape_counts`, tool-surface counts, `ordered_tool_pairs`, and fixture type counts expose the underlying shape of the 60 scenarios.
- `scenario_quality_warnings` is intentionally advisory. It does not affect `meets_assignment_minimums`; after the latest G3 pass the tracked D4, multi-turn, ordered-tool, and fixture-backed targets are all met, so the warning list is expected to stay empty.

## Later Enhancements

Community metadata such as GitHub stars, issue activity, adoption, and documentation quality can become later metadata signals. They should not affect G1-G2 deterministic scores.
