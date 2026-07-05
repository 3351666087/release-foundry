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

Media API calibration also checks tool-output grounding. A2-S031 uses `expectedToolOutputFacts` so a final answer must be supported by the `media.classify` output, not only by the final response text. The executable media set now covers pass, wrong classifier arguments, wrong tool order, and unsupported classifier output; these are summarized in the coverage report's `executable_media_*` and `executable_tool_output_grounding_*` fields.

Authenticated G3 calibration is optional and separate from deterministic unit tests. `scripts/a2_real_api_smoke.py` uses `ASHR_LABS_API_KEY` from the environment, performs read/list API calls, and writes only a redacted summary to `docs/evidence/a2_real_api_smoke.json`.

## Commercial-Grade A2 Goal Addendum

The July 4 commercial goal PDF upgrades A2 from an assignment checklist into a product-line evaluation system.

A2's commercial target is:

- keep the 60-scenario / 5-rubric / 5-judge / 20-golden / 12-failure minimums green,
- turn local rule judges into a calibratable judge engine,
- compare `local_judge`, future Ashr server-side `ashr_grading`, and `llm_judge` results on the same cases,
- record semantic/LLM judge cost and confidence instead of treating model calls as free or opaque,
- convert disagreements into regression fixtures or calibration follow-ups,
- keep evidence honest when a source is missing instead of fabricating high-fidelity results.

The first commercial-readiness artifact is `fixtures/a2/results/a2_g3_calibration_matrix.json`.
It currently includes six representative cases across pass control, argument fidelity, media/tool-output grounding, failure recovery, safety, and clarification.
The matrix deliberately marks `ashr_grading` as missing until a real server-side grading batch is collected.

The July 4 PDF gate logic is also encoded in `fixtures/a2/results/a2_commercial_readiness_report.json`.
This report marks C2 as met and C3-C5 as partial, because A2 can consume both Python and TypeScript SDK runner shapes and has a quota-aware batch plan, but still lacks reviewed Ashr grading observations, audited live LLM judge calls, and a mature case book/regression suite.

The first C1 SDK-parity artifact is `fixtures/a2/results/a2_sdk_parity_report.json`. It grades the same A2 scenario through a Python-style `AgentTurn` shape and a TypeScript-style `CaseResult.agent_output` shape so the official dual-SDK chain stays visible in A2.
It also records an `official_sdk_chains` map for the two Ashr quickstart routes: Python uses `EvalRunner.from_dataset(...)` / `run_and_deploy(...)`, while TypeScript uses `EvalRunner.fromDataset(...)` / `runAndDeploy(...)`. A2's responsibility is to keep both resulting runner-output shapes gradable, not to collapse the project into a Python-only clone.

The first C2 batch-plan artifact is `fixtures/a2/results/a2_batch_plan_report.json`. It defines local, SDK parity, Ashr grading, semantic judge, and regression replay batches and mirrors A1's queue-worker quota phases without requiring live API keys.

The first C4 semantic-harness artifact is `fixtures/a2/results/a2_semantic_harness_report.json`. It defines the prompt contract, output schema, model/cost/redaction policy, and six calibration cases for audited LLM judge calls. It explicitly keeps both Python `AgentTurn` and TypeScript `CaseResult.agent_output` prompt paths visible, including the media/tool-output grounding case. The current artifact is harness-ready but still marks live model evidence as missing.

`scripts/a2_import_semantic_judge.py` is the C4 import bridge. It converts reviewed semantic judge summaries into `llm_judge` observations with provider/model, cost, confidence, prompt/response hashes, review status, and SDK language. This lets A2 replace offline references with audited summaries later without committing raw prompts, raw model responses, API keys, or account-specific payloads.

`fixtures/a2/results/a2_evidence_readiness_report.json` is the C3/C4 preflight artifact. It lists the six calibration cases, verifies the Ashr grading case map covers them, records the reviewed import/merge commands, and names the semantic judge fields that must be present before offline references can be replaced. It is intentionally a readiness report, not external evidence. The `ashr_public_merge_gate` currently reports `status: not_merged`, so C3 remains partial until six reviewed Ashr grading observations are imported into the public calibration matrix and regenerated.

The first C5 case-book seed is `fixtures/a2/results/a2_case_book.json`, with a reviewer-readable companion at `docs/a2/case_book.md`. It currently promotes the `sample-a2-s010-wrong-arguments` local-vs-LLM failure-class disagreement into an explicit open regression seed.

The first C5 executable replay artifact is `fixtures/a2/results/a2_regression_replay_report.json`. It re-runs every case-book seed through deterministic `grade_run` and checks that local failure class preservation, pass/fail status, matrix disagreement visibility, and regression assertions still hold. The case book and replay report now expose `maturity_gate` fields: the target is 3 reviewed disagreement regressions, the current count is 1, and the status remains `seed` until more reviewed disagreements are promoted.

Next A2 priorities should be chosen by ROI against this commercial target:

1. collect a small authenticated Ashr grading batch and fill the `ashr_grading` column,
2. run the semantic harness with audited model calls and import reviewed `llm_judge` rows through the C4 bridge,
3. promote local-vs-LLM disagreements into regression fixtures or judge improvements.

`scripts/a2_import_ashr_grading.py` is the bridge for the first item. It converts redacted Ashr `run.result.tests[].action_results[]` records into `ashr_grading` observations with canonical A2 failure classes. Reviewed imports should be created with `--review-status reviewed`; otherwise the rows remain usable for inspection but cannot make `ashr_public_merge_gate.safe_to_mark_c3_met` true. `scripts/a2_merge_calibration_observations.py` is the review gate that merges those observations into the calibration payload after checking source and known case ids. Raw/private API records stay under `docs/evidence/private_refs`; committed A2 fixtures should only contain reviewed observation summaries and private evidence references.

`fixtures/a2/calibration/ashr_grading_batch_case_map.json` defines the six recommended Ashr `test_id` values for the current C3 calibration batch. It should be used when collecting the first real Ashr grading batch so `ashr_grading` rows join cleanly with A2 case ids.

The G3 coverage report also includes `assignment_minimums`, `assignment_checks`, `meets_assignment_minimums`, and calibration redundancy warnings. Thin coverage is not a failing condition by itself; it marks failure classes that only have the minimum calibration depth and should be prioritized in later iterations.

After the G3 calibration pass, both `thin_golden_failure_classes` and `thin_executable_failure_classes` are expected to stay empty, meaning every canonical failure class has at least two golden cases and at least two executable run fixtures.

For auditability, the coverage report also exposes `golden_failure_class_cases` and `executable_failure_class_cases`, which list the case/scenario evidence behind each canonical failure class count.

G3 now also audits scenario quality dimensions beyond the assignment minimums:

- `scenario_dimension_counts`, `scenario_dimension_checks`, and `scenario_dimension_scenarios` show coverage for task shapes such as required tool use, optional tool choice, forbidden-tool boundaries, ordered tool sequences, multi-turn dialogue, fixture grounding, clarification, failure recovery, safety, grounding/reference, argument fidelity, output contracts, freshness/current-info, and tool-output grounding.
- `capability_axis_counts`, `capability_axis_checks`, and `capability_axis_scenarios` group those detailed dimensions into reviewer-facing capability axes: tool choice/policy, multi-step workflow, clarification handling, failure recovery, safety boundary, grounding/reference, trace contract, output contract, freshness/external context, and media/multimodal coverage. `missing_capability_axes` is expected to stay empty.
- `difficulty_counts`, `action_count_counts`, `environment_counts`, `tag_counts`, `tool_policy_shape_counts`, tool-surface counts, `ordered_tool_pairs`, and fixture type counts expose the underlying shape of the 60 scenarios.
- `scenario_quality_warnings` is intentionally advisory. It does not affect `meets_assignment_minimums`; after the latest G3 pass the tracked D4, multi-turn, ordered-tool, and fixture-backed targets are all met, so the warning list is expected to stay empty.

## Later Enhancements

Community metadata such as GitHub stars, issue activity, adoption, and documentation quality can become later metadata signals. They should not affect G1-G2 deterministic scores.
