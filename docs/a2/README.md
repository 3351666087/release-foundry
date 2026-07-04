# A2 Scenario & Judge

Kay owns A2 for the Ashr reproduction project.

This module provides the local G1-G2 foundation for:

- scenario packs,
- `toolPolicy`,
- deterministic local judges,
- failure taxonomy,
- golden cases,
- sample run fixtures.

## Current Deliverables

- 20 G2 seed scenarios: `packages/scenarios/a2_g2_seed_pack.json`
- 60 G3 full scenarios: `packages/scenarios/a2_g3_full_pack.json`
- 32 golden cases: `fixtures/golden/a2_g2_golden_cases.json`
- 12 failure classes: `docs/a2/failure_taxonomy_v0.md`
- Tool policy judge: `services/judge/tool_policy.py`
- Output contract judge: `services/judge/outcome.py`
- Replay/trace recovery judge: `services/judge/trace_integrity.py`
- Grounding judge: `services/judge/grounding.py`
- Safety boundary judge: `services/judge/safety_boundary.py`
- Local runner: `services/judge/runner.py`
- Coverage report helper: `services/judge/coverage.py`
- Calibration matrix helper: `services/judge/calibration.py`
- Case book helper: `services/judge/casebook.py`
- SDK parity helper: `services/judge/sdk_parity.py`
- Semantic judge harness helper: `services/judge/semantic_harness.py`
- Commercial readiness helper: `services/judge/readiness.py`
- Generated fixture reproducibility check: `scripts/a2_regenerate_fixtures.py`
- A3 aggregate grade fixture: `fixtures/a2/results/a2_g3_grade_results.json`
- G3 coverage audit fixture: `fixtures/a2/results/a2_g3_coverage_report.json`
- G3 local/Ashr/LLM calibration matrix: `fixtures/a2/results/a2_g3_calibration_matrix.json`
- Case book regression seed: `fixtures/a2/results/a2_case_book.json`
- Python/TypeScript SDK parity report: `fixtures/a2/results/a2_sdk_parity_report.json`
- Quota-aware batch plan report: `fixtures/a2/results/a2_batch_plan_report.json`
- Semantic judge harness report: `fixtures/a2/results/a2_semantic_harness_report.json`
- Commercial readiness gate report: `fixtures/a2/results/a2_commercial_readiness_report.json`
- Scenario quality dimension audit and advisory warnings in the G3 coverage report
- A2/A3 handoff schema snapshots: `docs/a2/schemas/`
- 31 executable calibration run fixtures, including G3 tool/workflow/media cases in `fixtures/a2/runs`
- Optional real Ashr API smoke script: `scripts/a2_real_api_smoke.py`

## Local Run Shapes

A1 can hand A2 a run object like this:

```json
{
  "tool_calls": [
    {"id": "call-1", "tool": "web.search", "args": {"query": "Acme MiniDock official price"}}
  ],
  "final_response": "The official Acme MiniDock page lists the price as $79.",
  "expected_keywords": ["$79"],
  "forbidden_keywords": []
}
```

A2 also accepts A1's native local runner shapes directly:

- `agent_output` / `AgentTurn` with `text` and `tool_calls[].name` / `arguments`
- `CaseResult` with `case_id`, `scenario_id`, and nested `agent_output`
- OpenAI-style tool calls with `function.name` / `function.arguments`

`services.judge.runner.grade_run` normalizes those shapes into A2's internal `final_response` plus `tool_calls[].tool` / `args` form before judging.

A2 regrades behavior against its own `scenario_id` and `toolPolicy`; it does not inherit A1's existing `status`, `grade`, or `expected` result. Tool names are exact contract names such as `web.search` and `file.read`, not aliases like `search` or `read`.

A2 can grade it with:

```python
from services.judge.runner import grade_run

result = grade_run("A2-S004", run)
```

## SDK Parity

The Ashr docs expose both Python and TypeScript SDK entrypoints, so A2 must not silently become Python-only.

A2 now generates `fixtures/a2/results/a2_sdk_parity_report.json` from `services/judge/sdk_parity.py`. The report grades the same scenario through:

- Python-style `AgentTurn` / `AgentResult.to_dict()` metadata from `packages/sdk/ashr_clone/adapter.py`
- TypeScript-style `CaseResult.agent_output` metadata from `packages/ts/ashr-clone/src/index.ts`

This is deterministic contract evidence for C1: A2 can consume both SDK-language runner shapes. It does not claim hosted TypeScript API parity or live Ashr grading; those remain A1/C3 calibration work.

## Semantic Judge Harness

C4 needs a semantic judge path that is auditable before it is trusted.

A2 now generates `fixtures/a2/results/a2_semantic_harness_report.json` from `services/judge/semantic_harness.py`. This report defines:

- prompt input fields for scenario contract, `toolPolicy`, expected behavior, final response, tool calls, and observed tool results,
- required semantic judge output fields: `passed`, `primary_failure_class`, `score`, `confidence`, `rationale`, and `evidence_refs`,
- model, cost, and redaction policies for audited live model calls,
- per-case calibration targets for the six C3/C4 cases, including the media/tool-output grounding case,
- Python `AgentTurn` and TypeScript `CaseResult.agent_output` prompt paths.

The current harness is ready for audited model calls but still reports `live_model_evidence_available: false`. That is intentional: offline `llm_judge` samples are useful deterministic references, but C4 is not met until private live model evidence is reviewed and summarized.

## Batch Plan

C2 requires a batch generation plan and cost ledger before paid calibration scales up.

A2 now generates `fixtures/a2/results/a2_batch_plan_report.json` from `services/judge/batch_plan.py`. It plans five batches:

- full local scenario-pack regression,
- Python/TypeScript SDK parity smoke,
- tiny Ashr grading calibration batch,
- semantic/LLM judge audit batch across Python and TypeScript chains,
- case-book regression replay.

The report also records queue-style quota phases aligned with A1's local cloud worker direction: `run.submit` is planned at enqueue/direct-submit time, `observation.write` at completion, and status history must preserve queued/running/completed plus failed/cancelled terminal states. This is C2 planning evidence; it does not replace the missing C3 real Ashr grading observations.

The result contains:

- overall `passed`,
- average `score`,
- canonical `primary_failure_class` for A3 clustering,
- 5 per-judge `GradeResult` entries,
- nested `FailureAnalysis` objects for A3 display.

Local debug signals such as `bad_final_response` can appear inside `failure_analysis.failure_classes`, but they should not be used as the top-level `primary_failure_class`.

## Regenerating Fixtures

Generated A2 grade fixtures and the G3 coverage report are deterministic. Before handing results to A3, run:

```bash
python scripts/a2_regenerate_fixtures.py --check
```

If a scenario, judge, or calibration run intentionally changes, refresh the committed output with:

```bash
python scripts/a2_regenerate_fixtures.py --write
```

This script only uses local fixtures and does not require an Ashr API key.

## Commercial Calibration Matrix

G3 also keeps a calibration matrix for comparing:

- `local_judge`: deterministic A2 runner output,
- `ashr_grading`: future Ashr server-side grading output,
- `llm_judge`: audited semantic/LLM judge observations.

The current matrix is generated from `fixtures/a2/calibration/a2_g3_calibration_observations.json` and written to `fixtures/a2/results/a2_g3_calibration_matrix.json`.

It is intentionally honest about missing evidence: `ashr_grading` is marked missing until a server-side grading batch is collected. `llm_judge` observations are offline reference samples with cost metadata, so local tests stay deterministic while the contract is ready for real model calls later.

When a redacted Ashr `get-run` or `list-runs` record is available under private evidence, convert it into A2 observations with:

```bash
python scripts/a2_import_ashr_grading.py \
  --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json \
  --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json \
  --evidence-ref docs/evidence/private_refs/a2_ashr_get_run.redacted.json \
  --output docs/evidence/private_refs/a2_ashr_grading_import.review.json
```

After review, merge the imported summaries into a calibration payload:

```bash
python scripts/a2_merge_calibration_observations.py \
  --incoming docs/evidence/private_refs/a2_ashr_grading_import.review.json \
  --source ashr_grading \
  --min-count 6 \
  --output fixtures/a2/calibration/a2_g3_calibration_observations.json
```

Then refresh deterministic outputs with `python scripts/a2_regenerate_fixtures.py --write`.

The import and merge commands never need the raw API key in their arguments. Raw/private API records stay under `docs/evidence/private_refs`; committed A2 fixtures should only contain reviewed summaries and evidence refs.

## Case Book

C5 requires disagreements to become durable regression evidence, not only comments in a calibration matrix.

A2 now generates:

- machine-readable case book: `fixtures/a2/results/a2_case_book.json`
- reviewer-facing case book: `docs/a2/case_book.md`
- schema: `docs/a2/schemas/case_book.schema.json`

The current seed is `sample-a2-s010-wrong-arguments`, where local A2 identifies `wrong_arguments` and the offline LLM reference identifies `ignored_tool_result`. This remains open until reviewed Ashr grading or audited live LLM evidence resolves the judge boundary.

## Commercial Readiness Gate

The July 4 commercial-goals PDF is now tracked as a deterministic A2 readiness overlay:

- source code: `services/judge/readiness.py`
- schema: `docs/a2/schemas/commercial_readiness.schema.json`
- generated report: `fixtures/a2/results/a2_commercial_readiness_report.json`

The readiness report does not replace A2's grade, coverage, or calibration contracts. It summarizes the PDF's C0-C6 gate expectations, the current evidence snapshot, and the next three highest-ROI A2 moves. The current state is C2 met with C3-C5 still partial because SDK runner consumption and quota-aware batch planning are covered, the C4 semantic harness is ready, but Ashr grading evidence is missing, LLM evidence is offline-only, and the case book/regression suite is not mature yet.

## G1-G2 Boundary

G1-G2 is deterministic and local. It should not depend on real Ashr API access, LLM judge calls, or live external tools.

G3 can add Ashr server-side grading calibration after the local contract is stable. The current repo keeps deterministic tests local, while `scripts/a2_real_api_smoke.py` can run authenticated read/list API calls and write a redacted evidence summary when `ASHR_LABS_API_KEY` is provided.

## Agent Workflow

Recommended Codex workflow for this track:

1. Main supervisor thread owns the branch, final code edits, tests, commit, and push.
2. Background subAgents can run read-only audits or bounded disjoint patches.
3. A subAgent should not push directly unless the supervisor explicitly gives it an isolated branch and clear ownership.
4. Main supervisor integrates subAgent findings, checks schema drift, runs A2 tests, stages explicit paths, and pushes.

This keeps the work visible enough for review while avoiding four long-running visible design threads for every small iteration.
