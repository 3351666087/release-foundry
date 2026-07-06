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
- Regression replay helper: `services/judge/regression_replay.py`
- SDK parity helper: `services/judge/sdk_parity.py`
- Semantic judge harness helper: `services/judge/semantic_harness.py`
- Semantic judge import helper: `scripts/a2_import_semantic_judge.py`
- Commercial readiness helper: `services/judge/readiness.py`
- Generated fixture reproducibility check: `scripts/a2_regenerate_fixtures.py`
- A3 aggregate grade fixture: `fixtures/a2/results/a2_g3_grade_results.json`
- G3 coverage audit fixture: `fixtures/a2/results/a2_g3_coverage_report.json`
- G3 local/Ashr/LLM calibration matrix: `fixtures/a2/results/a2_g3_calibration_matrix.json`
- Case book regression seed: `fixtures/a2/results/a2_case_book.json`
- Case book regression replay report: `fixtures/a2/results/a2_regression_replay_report.json`
- Python/TypeScript SDK parity report: `fixtures/a2/results/a2_sdk_parity_report.json`
- Quota-aware batch plan report: `fixtures/a2/results/a2_batch_plan_report.json`
- Semantic judge harness report: `fixtures/a2/results/a2_semantic_harness_report.json`
- External evidence readiness report: `fixtures/a2/results/a2_evidence_readiness_report.json`
- Commercial readiness gate report: `fixtures/a2/results/a2_commercial_readiness_report.json`
- Scenario quality dimension audit and advisory warnings in the G3 coverage report
- A2/A3 handoff schema snapshots: `docs/a2/schemas/`
- 32 executable calibration run fixtures, including G3 tool/workflow/media cases in `fixtures/a2/runs`
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

In plain terms, these are two official ways to reach the same Testing Platform workflow:

- Python chain: `pip install ashr-labs` -> `AshrLabsClient` -> `EvalRunner.from_dataset(...)` -> `run_and_deploy(...)` -> A2 consumes `AgentTurn` / `AgentResult.to_dict()` output.
- TypeScript chain: `npm install ashr-labs` -> `new AshrLabsClient(...)` -> `EvalRunner.fromDataset(...)` -> `runAndDeploy(...)` -> A2 consumes `CaseResult.agent_output` output.

A2 now generates `fixtures/a2/results/a2_sdk_parity_report.json` from `services/judge/sdk_parity.py`. The report grades the same scenario through:

- Python-style `AgentTurn` / `AgentResult.to_dict()` metadata from `packages/sdk/ashr_clone/adapter.py`
- TypeScript-style `CaseResult.agent_output` metadata from `packages/ts/ashr-clone/src/index.ts`

The report also records `official_sdk_chains` so reviewers can see exactly how the official Python and TypeScript quickstart surfaces map into A2's local runner contract.

This is deterministic contract evidence for C1: A2 can consume both SDK-language runner shapes. It does not claim hosted TypeScript API parity or live Ashr grading; those remain A1/C3 calibration work.

## Media API Calibration

A2-S031 is the current media/tool-output grounding scenario. It now has four executable calibration cases:

- passing media pipeline,
- classifier output contradicts the final answer: `hallucinated_tool_result`,
- tool order is wrong: `wrong_tool_order`,
- media classifier API argument is wrong: `wrong_arguments`.

`fixtures/a2/results/a2_g3_coverage_report.json` exposes these through `executable_media_case_count`, `executable_tool_output_grounding_case_count`, `executable_media_expected_class_counts`, and the corresponding case refs. This keeps media coverage visible without changing the A3 grade-result contract.

## Semantic Judge Harness

C4 needs a semantic judge path that is auditable before it is trusted.

A2 now generates `fixtures/a2/results/a2_semantic_harness_report.json` from `services/judge/semantic_harness.py`. This report defines:

- prompt input fields for scenario contract, `toolPolicy`, expected behavior, final response, tool calls, and observed tool results,
- required semantic judge output fields: `passed`, `primary_failure_class`, `score`, `confidence`, `rationale`, and `evidence_refs`,
- model, cost, and redaction policies for audited live model calls,
- per-case calibration targets for the six C3/C4 cases, including the media/tool-output grounding case,
- Python `AgentTurn` and TypeScript `CaseResult.agent_output` prompt paths.

The current harness is ready for audited model calls but still reports `live_model_evidence_available: false`. That is intentional: offline `llm_judge` samples are useful deterministic references, but C4 is not met until private live model evidence is reviewed and summarized.

`scripts/a2_import_semantic_judge.py` is the bridge from reviewed private model-call summaries into the calibration matrix. It preserves provider/model, prompt and response hashes, prompt template id, cost, confidence, review status, and SDK language while redacting token-like or email-like text. The checked-in sample fixture is only an importer test shape; it is not counted as C4 live evidence.

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

## Evidence Readiness

C3/C4 need private evidence, but A2 should still make the collection workflow auditable before any key or account payload is used.

A2 now generates `fixtures/a2/results/a2_evidence_readiness_report.json` from `services/judge/evidence_readiness.py`. It records:

- the six calibration cases that need comparable external observations,
- whether `fixtures/a2/calibration/ashr_grading_batch_case_map.json` covers every calibration case,
- the public-safe A1 real API evidence index summary from `docs/a1/api_calibration/real_api_evidence_index.json`,
- the public-safe evidence index contract pinned by `docs/a2/schemas/evidence_index.schema.json`,
- the reviewed Ashr grading import/merge commands,
- an `ashr_public_merge_gate` that says whether the reviewed Ashr grading column is actually present in the public calibration matrix,
- the required semantic judge review fields, including provider/model, prompt/response hashes, cost, confidence, review status, and SDK language,
- the private evidence boundary: raw prompts, raw responses, account payloads, and API keys stay under `docs/evidence/private_refs/` and are not committed.

This report is readiness evidence only. It intentionally keeps C3/C4 partial until reviewed Ashr grading observations and audited live semantic judge observations are imported. `ready_for_external_collection: true` means the workflow is ready; it does not mean C3 is met. C3 is safe to mark met only when `ashr_public_merge_gate.safe_to_mark_c3_met` is true.

Before collecting or merging private evidence, run the offline preflight:

```bash
python scripts/a2_external_evidence_preflight.py --json
```

This command reads only public fixtures, does not require network or an Ashr API key, does not read `docs/evidence/private_refs/`, and writes nothing. Its JSON output uses `docs/a2/schemas/external_evidence_preflight.schema.json`. It summarizes C3/C4/C5 status, missing reviewed observations, private input refs, reviewed import commands, and the redaction policy so reviewers can confirm the next evidence step is safe before any private payload is touched.

If private API probes have already been collected, the same preflight JSON lists the public-safe index refresh command under `recommended_commands.real_api_evidence_refresh`. Run it before regenerating fixtures so A2/A3 readiness summaries reflect the latest redacted real API evidence without committing raw payloads.

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

## Local-Lite Check

For low-memory local verification, run:

```bash
python scripts/a2_local_lite_check.py
```

This profile runs only deterministic A2 fixture reproducibility and A2 unit/contract tests. It does not require `node_modules`, a browser, network access, or an Ashr API key. Use `python scripts/a2_local_lite_check.py --plan` to print the exact checks without running them.

## Commercial Calibration Matrix

G3 also keeps a calibration matrix for comparing:

- `local_judge`: deterministic A2 runner output,
- `ashr_grading`: future Ashr server-side grading output,
- `llm_judge`: audited semantic/LLM judge observations.

The current matrix is generated from `fixtures/a2/calibration/a2_g3_calibration_observations.json` and written to `fixtures/a2/results/a2_g3_calibration_matrix.json`.

It is intentionally honest about missing evidence: `ashr_grading` is marked missing until a server-side grading batch is collected. `llm_judge` observations are offline reference samples with cost metadata, so local tests stay deterministic while the contract is ready for real model calls later.

When a redacted Ashr `get-run` or `list-runs` record is available under private evidence, scan it first to confirm it really contains the six mapped C3 cases:

```bash
python scripts/a2_scan_ashr_grading_evidence.py \
  --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json \
  --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json
```

Only after the scanner reports `complete_expected_match: true` and the private evidence has been reviewed, convert it into A2 observations with:

```bash
python scripts/a2_import_ashr_grading.py \
  --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json \
  --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json \
  --evidence-ref docs/evidence/private_refs/a2_ashr_get_run.redacted.json \
  --review-status reviewed \
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

The import and merge commands never need the raw API key in their arguments. Raw/private API records stay under `docs/evidence/private_refs`; committed A2 fixtures should only contain reviewed summaries and evidence refs. C3 remains unsafe unless all six public `ashr_grading` rows include `metadata.review_status: reviewed` and a non-empty `evidence_ref`.

Reviewed semantic judge summaries use the same merge gate. Convert redacted model-call summaries into `llm_judge` observations with:

```bash
python scripts/a2_import_semantic_judge.py \
  --input docs/evidence/private_refs/a2_semantic_judge_review.redacted.json \
  --evidence-ref docs/evidence/private_refs/a2_semantic_judge_review.redacted.json \
  --output docs/evidence/private_refs/a2_semantic_judge_import.review.json
```

Then merge reviewed rows with:

```bash
python scripts/a2_merge_calibration_observations.py \
  --incoming docs/evidence/private_refs/a2_semantic_judge_import.review.json \
  --source llm_judge \
  --min-count 6 \
  --output fixtures/a2/calibration/a2_g3_calibration_observations.json
```

The importer expects reviewed summaries, not raw prompts or raw responses. Raw/private model payloads stay under `docs/evidence/private_refs`.

## Case Book

C5 requires disagreements to become durable regression evidence, not only comments in a calibration matrix.

A2 now generates:

- machine-readable case book: `fixtures/a2/results/a2_case_book.json`
- executable replay report: `fixtures/a2/results/a2_regression_replay_report.json`
- reviewer-facing case book: `docs/a2/case_book.md`
- schema: `docs/a2/schemas/case_book.schema.json`
- replay schema: `docs/a2/schemas/regression_replay.schema.json`

The current seed is `sample-a2-s010-wrong-arguments`, where local A2 identifies `wrong_arguments` and the offline LLM reference identifies `ignored_tool_result`. This remains open until reviewed Ashr grading or audited live LLM evidence resolves the judge boundary.

The case book now exposes a `candidate_pool` and `maturity_gate` so reviewers can see why C5 is still partial: the current calibration batch has 6 local-vs-LLM comparable cases, 1 mismatch promoted into the case book, and 6 missing Ashr grading observations. The maturity target is 3 reviewed disagreement regressions.

The replay report re-runs the seed through `grade_run` and checks that the local failure class, pass/fail status, matrix disagreement, and regression assertion are still visible. It currently reports `replay_ready: true` and `maturity_status: seed`, while `maturity_gate.ready: false` explains that 2 more reviewed replay cases are needed before C5 can be called mature.

## Commercial Readiness Gate

The July 4 commercial-goals PDF is now tracked as a deterministic A2 readiness overlay:

- source code: `services/judge/readiness.py`
- schema: `docs/a2/schemas/commercial_readiness.schema.json`
- generated report: `fixtures/a2/results/a2_commercial_readiness_report.json`

The readiness report does not replace A2's grade, coverage, or calibration contracts. It summarizes the PDF's C0-C6 gate expectations, the current evidence snapshot, and the next three highest-ROI A2 moves. The current state is C2 met with C3-C5 still partial because SDK runner consumption and quota-aware batch planning are covered, the C4 semantic harness is ready, and C5 replay is executable, but Ashr grading evidence is missing, LLM evidence is offline-only, and the case book/regression suite is not mature yet. The commercial snapshot also mirrors `ashr_public_merge_gate`, so C3 remains partial while `ashr_safe_to_mark_c3_met` is false.

The same report now includes `scope_boundary`, which explains why A2 is larger than A1/A3 and how that growth is constrained. A2 owns evaluation contracts, deterministic judges, calibration fixtures, and evidence gates. Hosted run execution, raw SDK/API collection, and cloud worker behavior remain A1-owned; dashboard UI, filtering, and presentation exports remain A3-owned. Additive audit fields, deterministic fixtures, and evidence gates are allowed growth, but live calls in local tests, runner orchestration, dashboard ownership, or breaking `a2.grade_results.v1` changes are blocked growth.

## G1-G2 Boundary

G1-G2 is deterministic and local. It should not depend on real Ashr API access, LLM judge calls, or live external tools.

G3 can add Ashr server-side grading calibration after the local contract is stable. The current repo keeps deterministic tests local, while `scripts/a2_real_api_smoke.py` can run authenticated read/list API calls and write a redacted evidence summary when `ASHR_LABS_API_KEY` is provided. The committed smoke summary uses `docs/a2/schemas/real_api_smoke.schema.json`.

After private A1/A2 API probes are recorded under ignored `docs/evidence/private_refs/`, refresh the public-safe evidence index with:

```bash
python -B scripts/a2_refresh_real_api_evidence_index.py --label a2-g3-real-api-refresh
python -B scripts/a2_regenerate_fixtures.py --write
```

The refresh script preserves already committed safe index rows when the local raw private evidence is unavailable, then merges any newly available private records by `path`. The committed index must contain only field keys, counts, statuses, quota summaries, and private evidence refs.
Its public shape is covered by `docs/a2/schemas/evidence_index.schema.json` and A2 contract tests, so A1/A3 can consume the same real API evidence summary without reading raw private payloads.

## Agent Workflow

Recommended Codex workflow for this track:

1. Main supervisor thread owns the branch, final code edits, tests, commit, and push.
2. Background subAgents can run read-only audits or bounded disjoint patches.
3. A subAgent should not push directly unless the supervisor explicitly gives it an isolated branch and clear ownership.
4. Main supervisor integrates subAgent findings, checks schema drift, runs A2 tests, stages explicit paths, and pushes.

This keeps the work visible enough for review while avoiding four long-running visible design threads for every small iteration.
