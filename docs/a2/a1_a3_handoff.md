# A1/A3 Handoff Contract

This page describes the current local G1-G2 handoff around Kay's A2 module.

## A1 -> A2 Run Input

A1 can produce a normalized A2 run object with tool calls and a final response:

```json
{
  "tool_calls": [
    {
      "id": "call-1",
      "tool": "file.read",
      "args": {"path": "fixtures/a2/notes/launch-review.md"}
    }
  ],
  "final_response": "Three grounded bullets...",
  "expected_keywords": [],
  "forbidden_keywords": []
}
```

Required fields for the normalized A2 shape:

- `tool_calls`: ordered list of tool calls. Use `tool` and `args`.
- `final_response`: assistant's final text.

Optional fields for G2 deterministic checks:

- `expected_keywords`: strings that should appear in the final response.
- `forbidden_keywords`: strings that should not appear in the final response.

## A1 Native Shapes

A2 now also accepts A1 local runner output directly. This lets A1 call A2 without pre-projecting every run by hand.

Accepted native A1 inputs:

1. `AgentTurn` / `agent_output`

```json
{
  "schema_version": "ashr.clone.agent_turn.v1",
  "text": "The grounded answer...",
  "tool_calls": [
    {
      "name": "file.read",
      "arguments": {"path": "fixtures/a2/notes/launch-review.md"},
      "call_id": "call-1"
    }
  ],
  "status": "ok",
  "latency_ms": 0,
  "metadata": {}
}
```

2. `CaseResult`

```json
{
  "case_id": "math-00",
  "scenario_id": "A2-S005",
  "status": "passed",
  "agent_output": {
    "schema_version": "ashr.clone.agent_turn.v1",
    "text": "The grounded answer...",
    "tool_calls": [{"name": "file.read", "arguments": {"path": "fixtures/a2/notes/launch-review.md"}}],
    "status": "ok",
    "latency_ms": 0,
    "metadata": {}
  }
}
```

`grade_run` normalizes A1 `text` into A2 `final_response`, and A1 `tool_calls[].name` / `arguments` into A2 `tool_calls[].tool` / `args`. It also accepts OpenAI-style `function.name` / `function.arguments` tool calls.

Boundary: A2 regrades the behavior against the `scenario_id` passed to `grade_run`; it does not inherit A1's `status`, `grade`, or `expected` fields. Tool names remain exact A2 contract names such as `web.search`, `web.open`, and `file.read`; alias mapping can be added later if A1/A3 agree on a shared tool registry.

## A2 Local Grading

```python
from services.judge.runner import grade_run

result = grade_run("A2-S005", run)
```

`grade_run` currently runs:

1. `ToolPolicyJudge`
2. `OutcomeJudge`
3. `TraceIntegrityJudge`
4. `GroundingJudge`
5. `SafetyBoundaryJudge`

The combined result includes:

- `passed`
- `score`
- canonical `primary_failure_class`
- `judge_results`

`primary_failure_class` is reserved for the 12 canonical A2 failure classes or `none`, so A3 failure clusters stay stable. Local debug signals can remain inside nested `failure_analysis.failure_classes`; A3 normalizes legacy local signals before clustering.

## A2 -> A3 Display Output

A3 can display:

- run pass/fail status,
- overall score,
- primary failure class,
- per-judge score,
- nested `failure_analysis.summary`,
- `evidence.tool_call_ids`,
- `evidence.final_response_excerpt`.

Sample outputs:

- `fixtures/a2/results/a2_s001_pass_grade.json`
- `fixtures/a2/results/a2_s004_missing_tool_grade.json`
- `fixtures/a2/results/a2_s010_wrong_arguments_grade.json`

For dashboard/report consumption, A2 also provides an aggregate wrapper:

- `fixtures/a2/results/a2_g3_grade_results.json`
- `fixtures/a2/results/a2_g3_coverage_report.json`
- `fixtures/a2/results/a2_g3_calibration_matrix.json`

The aggregate wrapper uses:

- `schema_version`: `a2.grade_results.v1`
- `grade_results[]`: list of normal `grade_run` outputs
- `total_cases`, `passed`, `failed`
- `scenario_pack`, `dataset_id`, `report_id`

A2 aggregate scores use a 0-100 scale with `max_score: 100` on per-judge results. A3 also normalizes A1 nested `case.grade.score` values on the 0-1 scale when no A2 aggregate grade is joined.

The coverage wrapper uses `schema_version: a2.coverage_report.v1` and lets A3 display scenario/rubric/judge coverage, golden case coverage, executable failure calibration coverage, assignment minimum checks, and thin-calibration warnings without rerunning A2 code.

A3 can also use `golden_failure_class_cases` and `executable_failure_class_cases` as drilldown evidence for each canonical failure class. The Markdown report surfaces the same evidence in a compact `Failure Class Evidence` section for manual review.

For scenario-quality review, A3 can read `scenario_dimension_counts`, `scenario_dimension_scenarios`, tool-surface counts, fixture type counts, and `scenario_quality_warnings`. The Markdown report surfaces the advisory warning details, but these warnings do not change `meets_assignment_minimums`.

The calibration matrix uses `schema_version: a2.calibration_matrix.v1`. It is a G3 commercial-readiness artifact for comparing `local_judge`, future `ashr_grading`, and `llm_judge` observations on the same cases. It exposes source coverage, agreement summaries, per-case diffs, cost ledger rows, and calibration warnings. A3 can surface this as a calibration panel without treating missing Ashr grading as a broken local test.

A1 can feed real Ashr run evidence into this matrix by first storing raw/redacted `get-run` or `list-runs` records under ignored private evidence, then using `scripts/a2_import_ashr_grading.py --review-status reviewed` to convert `run.result.tests[].action_results[]` into reviewed `ashr_grading` observations. The importer maps Ashr `test_id` values to A2 `case_id` values through a small JSON case map, preserving only summary fields such as score, canonical failure class, match statuses, run id, review status, and private evidence path.

For the current six-case C3 batch, A1 should use `fixtures/a2/calibration/ashr_grading_batch_case_map.json` when assigning Ashr `test_id` values. After A2 reviews the importer output, `scripts/a2_merge_calibration_observations.py` can merge those observations into `fixtures/a2/calibration/a2_g3_calibration_observations.json` with `--source ashr_grading --min-count 6`. C3 is still unsafe if the six public rows are merely present but do not carry `metadata.review_status: reviewed` and an `evidence_ref`.

The commercial readiness report uses `schema_version: a2.commercial_readiness.v1` and lives at `fixtures/a2/results/a2_commercial_readiness_report.json`. It is an optional planning/status feed for A3: it records the PDF-derived C0-C6 gate status, current evidence snapshot, commercial dimensions, and A2 next top 3. It is intentionally additive; A1/A3 should not depend on it for the existing grade or coverage join paths.

The case book uses `schema_version: a2.case_book.v1` and lives at `fixtures/a2/results/a2_case_book.json`. It is another optional feed for A3 or manual review: it promotes calibration disagreements into explicit regression seeds with local-vs-LLM failure class summaries, evidence refs, reviewer notes, a regression assertion, a `candidate_pool`, and a `maturity_gate`. A3's report builder can combine it with the replay report into a `regression_readiness` summary, and missing case-book data must not break existing dashboard/report paths.

The regression replay report uses `schema_version: a2.regression_replay.v1` and lives at `fixtures/a2/results/a2_regression_replay_report.json`. It is optional C5 evidence for A3/manual review: it re-runs case-book seeds through the deterministic local judge and reports whether the local failure class, pass/fail status, matrix disagreement, regression assertion, and replay maturity gate are still preserved. A3 exports can include its maturity status and replay gaps, and missing replay data must not break existing dashboard/report paths.

The SDK parity report uses `schema_version: a2.sdk_parity.v1` and lives at `fixtures/a2/results/a2_sdk_parity_report.json`. It is optional evidence for A1/A3 that A2 can consume both Python `AgentTurn` output and TypeScript `CaseResult.agent_output` shapes without changing the grade-result schema. Missing SDK-parity data must not break existing A3 dashboard/report paths.

The official SDK-language matrix is a first-class A2 boundary: Python and TypeScript are parallel entrypoints, not primary/secondary tiers. Any future Ashr grading, semantic judge, or report evidence should preserve the `python` plus `typescript` chain map unless a coordinated contract update says otherwise.

The semantic harness report uses `schema_version: a2.semantic_harness.v1` and lives at `fixtures/a2/results/a2_semantic_harness_report.json`. It is optional C4 evidence for A1/A3: it records the semantic judge prompt contract, output schema, model/cost/redaction policy, six calibration cases, and both Python `AgentTurn` and TypeScript `CaseResult.agent_output` prompt paths. It is harness-ready but not live-evidence-complete until audited model-call summaries replace offline references.

`scripts/a2_import_semantic_judge.py` converts reviewed semantic judge summaries into `llm_judge` calibration observations. A1/A3 do not need to run it for normal local tests; it is a bridge for private/reviewed C4 evidence and preserves only summary fields, costs, hashes, confidence, SDK language, and evidence refs.

The batch plan report uses `schema_version: a2.batch_plan.v1` and lives at `fixtures/a2/results/a2_batch_plan_report.json`. It is optional C2 planning evidence for A1/A3: it names planned local, SDK parity, Ashr grading, semantic judge, and regression replay batches; records expected quota phases; and keeps private evidence boundaries explicit. Missing batch-plan data must not break existing A3 dashboard/report paths.

The evidence readiness report uses `schema_version: a2.evidence_readiness.v1` and lives at `fixtures/a2/results/a2_evidence_readiness_report.json`. It is optional C3/C4 preflight evidence for A1/A3: it lists the six calibration cases, verifies the Ashr grading case map, records reviewed import/merge commands, names required semantic judge review fields, documents the private evidence boundary, and exposes `ashr_public_merge_gate.safe_to_mark_c3_met`. A3's report builder can summarize it when supplied, but it is not live Ashr or LLM evidence, and missing readiness data must not break existing A3 dashboard/report paths.

Commercial-readiness invariants:

- `grade_run` remains deterministic and local; live Ashr or LLM calls enter calibration/readiness artifacts only.
- A2 keeps `a2.grade_results.v1`, `a2.coverage_report.v1`, and `a2.calibration_matrix.v1` required fields stable unless a coordinated `v2` change request is made.
- Top-level `primary_failure_class` remains one of the canonical A2 failure classes or `none`; semantic disagreements belong in nested evidence, tags, or calibration artifacts.
- A3 may load `a2.commercial_readiness.v1`, `a2.case_book.v1`, `a2.regression_replay.v1`, `a2.sdk_parity.v1`, `a2.batch_plan.v1`, `a2.semantic_harness.v1`, or `a2.evidence_readiness.v1` as optional feeds, but missing optional readiness data must not break existing dashboard/report paths.
- `a2_commercial_readiness_report.json.scope_boundary` is the reviewer-facing bloat guard: A2 owns evaluation contracts and evidence gates, A1 owns hosted execution and raw API collection, and A3 owns dashboard/report UX. A2 growth should stay additive and test-backed.

## Known Boundary

This is primarily a local deterministic handoff. A2 now also keeps an optional real Ashr API smoke path in `scripts/a2_real_api_smoke.py`: when `ASHR_LABS_API_KEY` is set, it validates authentication and read/list endpoint reachability, then stores only a redacted summary in `docs/evidence/a2_real_api_smoke.json`. Hosted/server-side grading with `run.deploy` remains a later calibration step.

## Recommended Codex Workflow

Use the current thread as the main supervisor/integrator. Use background subAgents for narrow audits or disjoint implementation slices, then let the supervisor review, test, commit, and push. Visible threads are useful for long design discussions, but routine A1/A2/A3 compatibility passes can use hidden subAgents so the work stays fast and the Git history stays controlled.
