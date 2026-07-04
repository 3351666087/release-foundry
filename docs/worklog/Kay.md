# Kay A2 Worklog

## 2026-07-03 - Supervisor kickoff

Role: Kay, A2 / Scenario & Judge.

Long-running goal:
- Build the Ashr A2 G1-G2 foundation on branch `dev/a2-scenario-judge`.
- Final target: 60 scenarios, 5 rubric classes, 5 judge modes, 20 golden cases, 12 failure classes.
- Current foundation target: scenario/rubric/judge/failure taxonomy v0, first 20 scenarios, 2 local judges, golden seeds, tests, and A1/A3-compatible JSON outputs.

Supervisor setup:
- GitHub CLI installed and authenticated as `KayZhongyi`.
- Repository cloned locally under `work/ashr-codex-factory`.
- Branch created: `dev/a2-scenario-judge`.
- Heartbeat automation created for 15-minute self-checks.
- Subagents launched:
  - Research Agent: read-only evaluation design recommendations.
  - Scenario Worker: `packages/scenarios`, `docs/a2`.
  - Judge Worker: `services/judge`, `tests/a2`.
  - Failure/Golden Worker: `fixtures/golden`, `docs/a2`.

Scope rules:
- Kay-owned write paths: `packages/scenarios`, `services/judge`, `fixtures/golden`, `tests/a2`, `docs/a2`, `docs/worklog`.
- Do not modify A1/A3 paths.
- Do not directly modify shared schemas without a change request.

Evaluation principle:
- Score each scenario by what that scenario requires.
- Do not reward calling every tool.
- Tool policy must distinguish `required`, `optional`, and `forbidden` tools.
- Later enhancements may include external quality signals such as GitHub stars, but G1-G2 focuses on deterministic, reproducible local evaluation.

## 2026-07-03 - Visible-thread architecture revision

Reason for revision:
- Hidden subagents were less visible to Kay and one worker wrote draft files outside the target repo because the patch path did not stay anchored to `work/ashr-codex-factory`.
- Architecture was paused before any commit/push.

Revised execution model:
1. Current thread remains the main A2 supervisor and the only code integrator.
2. Visible Codex threads are used for read-only design first:
   - A2 Research Design
   - A2 Scenario Design
   - A2 Judge Design
   - A2 Failure & Golden Design
3. Design threads must not edit files, run git write commands, commit, push, or spawn more agents.
4. Main supervisor collects their reports, then writes code in the target repo with explicit `workdir` and scoped file changes.
5. Main supervisor runs tests, checks `git status` / `git diff`, updates worklog, and only then commits/pushes Kay-owned paths.

Transition plan:
- Early phase: one integration branch `dev/a2-scenario-judge`; visible threads are read-only.
- After schema v0 and G2 local loop stabilize, optional later phase can split implementation branches by module, such as `dev/a2-scenarios`, `dev/a2-judge`, and `dev/a2-golden`.
- Branch split is postponed until field names and output contracts are stable, to avoid schema drift.

Safety rules:
- Keep heartbeat paused or check-only until Kay asks for autonomous continuation.
- Do not use `git add .`.
- Do not use external social signals such as GitHub stars as G1-G2 scoring criteria; keep them as possible later metadata only.
- Treat repo-outside generated files as scratch only unless deliberately reviewed and copied into the target repo.

Visible design threads created:
- Research: 019f286a-42ec-7a93-8e81-3a0b971d442b
- Scenario: 019f286a-54cd-7e73-b3b8-7665bc07c21c
- Judge: 019f286a-66d3-72a3-ab68-7e4e26fd7a49
- Failure/Golden: 019f286a-78ad-7e81-9cca-62b1e03ec84d

## 2026-07-03 - A2 G1-G2 foundation implementation

Visible design reports completed and were consistent on:
- `toolPolicy` with required / optional / forbidden tools.
- G1-G2 deterministic local judges before G3 Ashr server-side calibration.
- First 20 seed scenarios as the G2 starter pack.
- 5 rubric classes, 5 judge modes, 12 failure classes, and 20 golden cases.

Implemented in Kay-owned paths:
- `docs/a2/scenario_schema.md`
- `docs/a2/scenario_coverage_plan.md`
- `docs/a2/failure_taxonomy_v0.md`
- `packages/scenarios/a2_g2_seed_pack.json`
- `fixtures/golden/a2_g2_golden_cases.json`
- `services/judge/*`
- `tests/a2/test_judges.py`

Local judge foundation:
- `ToolPolicyJudge`: checks required tools, optional tools, forbidden tools, exact/contains argument rules, and tool order.
- `OutcomeJudge`: checks deterministic final response constraints such as expected keywords, forbidden keywords, and no-tool response contracts.

Verification:
- `python -m json.tool packages/scenarios/a2_g2_seed_pack.json`
- `python -m json.tool fixtures/golden/a2_g2_golden_cases.json`
- `python -m unittest discover -s tests/a2 -v`
- Result: 8 tests passed.

Remaining gaps:
- G2 still needs richer fixture files for referenced paths.
- Judges are deterministic seeds, not yet semantic LLM judges.
- A1 runner integration and A3 dashboard consumption are pending other tracks.
- G3 Ashr API/server-side grading calibration is intentionally deferred.

## 2026-07-03 - A2 self-contained fixture and runner pass

Goal:
- Make the first A2 G2 seed pack self-contained enough for A1/A3 handoff.
- Remove dangling `fixtureRefs`.
- Add a local judge runner that returns a combined A2 result.

Implemented:
- Added mock fixtures under `fixtures/a2` for contracts, CSV sales data, MCP resource, notes, shell output, text prompts, web pages, and image placeholder.
- Added `services/judge/runner.py` with `load_scenario_pack`, `get_scenario`, and `grade_run`.
- Added `tests/a2/test_contracts.py` to verify:
  - exactly 20 seed scenarios,
  - all scenarios have `toolPolicy`,
  - all `fixtureRefs` exist,
  - golden cases cover all seed scenarios,
  - failure taxonomy includes the 12 required classes,
  - local runner returns a combined result.

Verification:
- `python -m json.tool packages/scenarios/a2_g2_seed_pack.json`
- `python -m json.tool fixtures/golden/a2_g2_golden_cases.json`
- `python -m unittest discover -s tests/a2 -v`
- Result: 13 tests passed.

Next likely improvements:
- Add a sample run JSON fixture that A1 can imitate.
- Add a short A2 README showing how to call `grade_run`.
- Later, add semantic/reference judge once G3 calibration starts.

## 2026-07-03 - A2 usage docs and sample runs

Goal:
- Make A2 easier for A1/A3 teammates to consume.

Implemented:
- Added `docs/a2/README.md` with current deliverables, run shape, and `grade_run` usage.
- Added sample run fixtures:
  - `fixtures/a2/runs/a2_s001_pass.json`
  - `fixtures/a2/runs/a2_s004_missing_tool.json`
- Extended contract tests to grade sample run fixtures and compare expected pass/fail plus primary failure class.

Verification:
- `python -m json.tool fixtures/a2/runs/a2_s001_pass.json`
- `python -m json.tool fixtures/a2/runs/a2_s004_missing_tool.json`
- `python -m unittest discover -s tests/a2 -v`
- Result: 14 tests passed.

## 2026-07-03 - A1/A3 handoff examples

Goal:
- Make A2 outputs easy for A1 and A3 to consume without reading implementation internals.

Implemented:
- Added `docs/a2/a1_a3_handoff.md` with the current A1 run input and A3 display output contract.
- Generated sample grade result fixtures under `fixtures/a2/results`.
- Extended contract tests so sample result fixtures must match `grade_run` output exactly.

Verification:
- `python -m json.tool fixtures/a2/results/a2_s001_pass_grade.json`
- `python -m json.tool fixtures/a2/results/a2_s004_missing_tool_grade.json`
- `python -m unittest discover -s tests/a2 -v`
- Result: 15 tests passed.

## 2026-07-04 - A1 native output compatibility pass

Reason:
- A1 added a local SDK/runner loop on `origin/codex/a1-local-sdk-runner`.
- A1's native output uses `AgentTurn` / `CaseResult` with `text` and `tool_calls[].name` / `arguments`, while A2 originally documented only `final_response` and `tool_calls[].tool` / `args`.

Implemented:
- Added A2-side run normalization in `services/judge/runner.py`.
- `grade_run` now accepts:
  - existing A2 normalized run objects,
  - A1 `AgentTurn` / `agent_output`,
  - A1 `CaseResult` with nested `agent_output`.
- Added compatibility for OpenAI-style `function.name` / `function.arguments` tool calls.
- Preserved JSON-string `function.arguments` so exact argument checks still work.
- Added contract tests for A1 native `agent_output` and `CaseResult` shapes.
- Updated A2 README and A1/A3 handoff docs.

Workflow update:
- Keep current thread as the main supervisor/integrator.
- Use background subAgents for read-only audits or narrow disjoint implementation tasks.
- Main supervisor owns final code review, tests, explicit staging, commit, and push.
- Visible Codex threads are optional for long design discussions, not required for every iteration.
- A read-only subAgent review caught the `function.arguments` string compatibility risk before push.

Boundary:
- A2 regrades behavior and does not inherit A1 `status`, `grade`, or `expected`.
- Tool names remain exact A2 contract names; no alias mapping is added in G1-G2.
- Do not merge the A1 branch into the A2 branch yet; keep structure compatibility until the integration branch/Gate review.

Verification:
- `python -m unittest discover -s tests/a2 -v`
- Result: 18 tests passed.

## 2026-07-04 - G3 A2 minimum coverage pass

Goal:
- Move A2 from the 20-scenario G2 seed into the G3 minimum assignment target.
- Keep the work local and deterministic before using real Ashr API credentials.

Implemented:
- Added `packages/scenarios/a2_g3_full_pack.json` with 60 scenarios:
  - 10 `direct_answer`
  - 10 `retrieval_grounding`
  - 10 `tool_execution`
  - 10 `workflow_planning`
  - 10 `safety_policy`
  - 10 `ambiguous_or_conflicting`
- Expanded runner output to 5 judge modes:
  - `g1_trace_contract_judge`
  - `g2_output_contract_judge`
  - `g3_replay_sandbox_judge`
  - `g3_semantic_reference_judge`
  - `g3_safety_boundary_judge`
- Added deterministic judges for replay/trace recovery, grounding facts, and safety boundaries.
- Added A2-S010 wrong-arguments run/result fixtures so A3 failure clustering no longer depends only on synthetic A3 data.
- Added `fixtures/a2/results/a2_g3_grade_results.json` aggregate grade report for A3.
- Added `services/judge/coverage.py` for assignment coverage reporting.

SubAgent review impact:
- A3 review identified the need for an aggregate `grade_results[]` wrapper.
- Judge review identified mode naming, grounding fact placement, and fixture/test drift.

Verification:
- `python -m unittest discover -s tests/a2 -v`
- `node --test tests/a3/report_builder.test.mjs`

## 2026-07-04 - Commercial A2 calibration matrix pass

Reason:
- Kay provided `Ashr_Commercial_Grade_Goals_CN.pdf`, which changes A2's working target from "meet G3 minimums" to "build a commercial-grade semantic evaluation product line."
- The PDF specifically names A2's next P1 as `semantic judge + calibration matrix`, with `LLM judge harness`, `Ashr/local/LLM diff table`, misjudgment regression fixtures, `eval report`, `cost ledger`, and `judge tests`.

Updated A2 goal interpretation:
- Keep all hard minimums green: 60 scenarios, 5 rubric classes, 5 judge modes, 20+ golden cases, and 12 canonical failure classes.
- Add commercial calibration evidence on top: compare deterministic `local_judge`, future Ashr server-side `ashr_grading`, and `llm_judge` observations on the same cases.
- Be explicit when evidence is missing. Current read/list Ashr API smoke is not the same as server-side grading, so `ashr_grading` remains marked missing until a real grading batch exists.
- Track model/cost/confidence metadata for semantic judging instead of treating LLM judge outputs as opaque.

Implemented:
- Added `services/judge/calibration.py` to build `a2.calibration_matrix.v1`.
- Added `fixtures/a2/calibration/a2_g3_calibration_observations.json` with six representative cases and offline `llm_judge` reference observations.
- Added generated result fixture `fixtures/a2/results/a2_g3_calibration_matrix.json`.
- Added `docs/a2/schemas/calibration_matrix.schema.json`.
- Extended `scripts/a2_regenerate_fixtures.py` so `--check` and `--write` include the calibration matrix.
- Updated `docs/a2/README.md`, `docs/a2/a1_a3_handoff.md`, and `docs/a2/scenario_coverage_plan.md` with the PDF-aligned commercial target.
- Added tests that verify source coverage, local-vs-LLM agreement, cost ledger fields, schema shape, and the intentionally tracked disagreement case.

Current matrix facts:
- `local_judge`: 6/6 available.
- `llm_judge`: 6/6 offline reference observations available.
- `ashr_grading`: 0/6 available, intentionally missing until real server-side grading evidence exists.
- `local_judge` vs `llm_judge`: 6 comparable cases, 1 failure-class disagreement on `sample-a2-s010-wrong-arguments`.

Peer/GitHub context:
- `gh pr list --state all` showed A1 draft PR #6, merged A3 P3 PR #5, and prior A1/A2/A3 merged PRs.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` initially hit a transient network reset, then succeeded.
- `origin/main` now includes merged A1/A3 work and diverges from this A2 branch; this pass did not merge main to avoid mixing peer changes into a scoped A2 commit.

Verification:
- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- `python -B -m unittest discover -s tests/a1 -v`
- `node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs`
- `git diff --check`

Next top 3:
1. Collect a small authenticated Ashr grading batch and fill the `ashr_grading` column.
2. Replace offline `llm_judge` observations with audited model calls and real cost evidence.
3. Promote the `wrong_arguments` vs `ignored_tool_result` disagreement into a regression case or judge calibration note.

## 2026-07-04 - Ashr grading import bridge

Reason:
- The commercial matrix pass made `ashr_grading` visible but still missing. The next useful step is a deterministic bridge from real Ashr `get-run/list-runs` evidence into A2 calibration observations.
- A1 on `origin/main` already has API probe support for `create-run`, `get-run`, `poll-run`, and redacted private evidence. A3 P3 already mapped real Ashr `run.result.tests[].action_results[]` fields. A2 needs its own small importer so it can fill the matrix without copying raw private records.

Implemented:
- Extended `services/judge/calibration.py` with `import_ashr_grading_observations(...)` and Ashr run extraction/classification helpers.
- Added `scripts/a2_import_ashr_grading.py`, a local CLI that converts a redacted Ashr run record plus a `test_id` to `case_id` map into `ashr_grading` observations.
- Added synthetic redacted import fixtures:
  - `fixtures/a2/calibration/ashr_grading_import_sample.json`
  - `fixtures/a2/calibration/ashr_grading_import_case_map.json`
- Added tests proving imported Ashr observations can raise matrix `ashr_grading` coverage from 0/6 to 2/6 and agree with local judge on the two mapped sample cases.
- Updated README, handoff docs, and scenario coverage plan with the importer workflow.

Boundary:
- This pass does not call the real Ashr API and does not read any key file.
- Raw/private API evidence should remain under `docs/evidence/private_refs`; committed A2 fixtures should contain only reviewed summaries and evidence refs.
- The current committed calibration matrix still marks `ashr_grading` as missing until a real batch is reviewed and merged.

Verification:
- `python -B scripts/a2_import_ashr_grading.py --input fixtures/a2/calibration/ashr_grading_import_sample.json --case-map fixtures/a2/calibration/ashr_grading_import_case_map.json --evidence-ref docs/evidence/private_refs/a2_ashr_grading_sample.redacted.json`
- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`

Next top 3:
1. Use A1's real API probe to collect a tiny private `get-run` or `poll-run` record for A2 mapped cases.
2. Run `scripts/a2_import_ashr_grading.py` against that private evidence and review the imported observations.
3. Merge reviewed `ashr_grading` observations into `a2_g3_calibration_observations.json` and regenerate the matrix.

## 2026-07-04 - Commercial readiness gate from new PDF

Reason:
- The new `Ashr_Commercial_Grade_Goals_CN.pdf` raises A2 from assignment minimums to a commercial-grade semantic evaluation product line.
- The PDF's A2 success condition is not just 60 scenarios; it is failing real agents for the right reasons and explaining those reasons under calibration evidence.

Implemented:
- Added `services/judge/readiness.py` to summarize PDF-derived C0-C6 commercial gate status from deterministic A2 coverage and calibration artifacts.
- Added generated report `fixtures/a2/results/a2_commercial_readiness_report.json`.
- Added schema snapshot `docs/a2/schemas/commercial_readiness.schema.json`.
- Integrated the report into `scripts/a2_regenerate_fixtures.py`, so `--check` now protects 35 A2 generated fixtures.
- Added tests for C0/C3/C4 status, missing Ashr grading evidence, offline-only LLM evidence, and the next top 3.
- Updated A2 README, scenario coverage plan, and A1/A3 handoff docs.
- Added contract invariants so commercial upgrades remain additive and do not break A1/A3 grade or coverage consumers.

Current commercial gate:
- C0 is met: assignment minimums, coverage, scenario quality, golden cases, and executable failures are stable.
- C3 is partial: local-vs-LLM diff exists, but all six calibration cases still lack reviewed Ashr server-side grading.
- C4 is partial: LLM judge confidence/cost fields exist, but current samples are offline references, not audited live model calls.
- C5 is partial: a judge disagreement candidate exists, but it has not yet been promoted into a regression fixture and case-book entry.

Next top 3:
1. Fill the `ashr_grading` column with a tiny reviewed private Ashr grading batch.
2. Replace offline LLM references with audited semantic judge calls and prompt/model/cost evidence.
3. Promote the current local-vs-LLM disagreement into regression fixtures and a case-book seed.

## 2026-07-04 - Ashr grading batch merge gate

Reason:
- The importer made Ashr grading evidence convertible, but filling C3 still required manual copying into `a2_g3_calibration_observations.json`.
- The current environment has no `ASHR_LABS_API_KEY`, so this round cannot safely run live Ashr. The useful step is to make the post-evidence merge deterministic and reviewable.

Implemented:
- Added `merge_calibration_observations(...)` to `services/judge/calibration.py`.
- Added `scripts/a2_merge_calibration_observations.py` so reviewed importer output can be merged with source and known-case validation.
- Added `fixtures/a2/calibration/ashr_grading_batch_case_map.json` with the six C3 calibration test ids.
- Added tests for six-case map coverage, function-level merge, CLI merge, and the resulting matrix coverage.
- Updated README, A1/A3 handoff, scenario coverage plan, and readiness next top 3.

Boundary:
- No real API call was made in this round because the key is not in the environment.
- The committed calibration matrix still marks `ashr_grading` missing until a reviewed real batch is merged.

Next top 3:
1. Export or collect a private real Ashr `get-run/list-runs` record using the six batch test ids.
2. Run importer -> merge gate with `--min-count 6`, then regenerate fixtures.
3. Promote any Ashr/local/LLM disagreements into regression fixtures or case-book entries.

## 2026-07-04 - Case book regression seed

Reason:
- The readiness report marked C5 partial because the calibration matrix had a disagreement candidate but no durable reviewer-facing case book.
- `sample-a2-s010-wrong-arguments` is the first useful seed: local A2 classifies the issue as `wrong_arguments`, while the offline LLM reference labels it `ignored_tool_result`.

Implemented:
- Added `services/judge/casebook.py` to build `a2.case_book.v1` from calibration disagreement tags.
- Added generated fixture `fixtures/a2/results/a2_case_book.json`.
- Added reviewer-facing markdown `docs/a2/case_book.md`.
- Added schema snapshot `docs/a2/schemas/case_book.schema.json`.
- Integrated case-book generation into `scripts/a2_regenerate_fixtures.py`.
- Updated commercial readiness to expose `case_book_regression_count`.
- Added tests that lock the generated case book, schema, markdown seed, and readiness count.

Boundary:
- This does not change `grade_run`, top-level `primary_failure_class`, or the A3 grade join.
- C5 remains partial because this is one regression seed, not a mature regression suite.

Next top 3:
1. Resolve the seed with reviewed Ashr grading or audited live LLM evidence.
2. Add any new Ashr/local/LLM disagreements to the case book automatically.
3. Let A3 optionally surface `a2_case_book.json` in a judge drilldown panel.

## 2026-07-04 - Python and TypeScript SDK parity evidence

Reason:
- The commercial-goals PDF and official Ashr docs treat Python and TypeScript as two SDK entrypoints.
- A2 should prove its judge runner can consume both SDK-language output shapes, not only Python-style fixtures.

Implemented:
- Merged latest `origin/main`, including A1's TypeScript SDK package under `packages/ts/ashr-clone`.
- Added `services/judge/sdk_parity.py` to build deterministic `a2.sdk_parity.v1` evidence.
- Added generated fixture `fixtures/a2/results/a2_sdk_parity_report.json`.
- Added schema snapshot `docs/a2/schemas/sdk_parity.schema.json`.
- Integrated SDK parity into `scripts/a2_regenerate_fixtures.py`.
- Updated commercial readiness so C1 is met when Python and TypeScript runner shapes both pass A2 grading.
- Added A2 tests for TypeScript `CaseResult.agent_output` consumption and SDK parity report reproducibility.

Boundary:
- This is A2 contract evidence, not a claim that A2 owns TypeScript SDK implementation.
- Hosted TypeScript API parity and real Ashr server-side grading remain A1/C3 calibration work.

Next top 3:
1. Keep the SDK parity report green as A1 changes Python or TypeScript runner schemas.
2. Fill the `ashr_grading` column with reviewed Ashr evidence for the six calibration cases.
3. Replace offline LLM references with audited model-call evidence and cost/provenance metadata.

## 2026-07-04 - C2 quota-aware batch plan

Reason:
- The commercial-goals PDF requires A2 to move beyond static fixtures into batch generation and cost/quota planning.
- A1's draft queue-worker direction exposes queued/running/completed lifecycle and quota phases that A2 should be ready to consume.

Implemented:
- Added `services/judge/batch_plan.py` to build deterministic `a2.batch_plan.v1` planning evidence.
- Added generated fixture `fixtures/a2/results/a2_batch_plan_report.json`.
- Added schema snapshot `docs/a2/schemas/batch_plan.schema.json`.
- Integrated batch-plan generation into `scripts/a2_regenerate_fixtures.py`.
- Updated commercial readiness so C2 is met when batch plan and calibration cost ledger both exist.
- Added A2 tests for batch membership, quota phases, schema coverage, and C2 readiness status.

Boundary:
- This is a plan and quota ledger artifact, not real paid calibration evidence.
- C3 remains partial until reviewed Ashr server-side grading observations are imported and merged.

Next top 3:
1. Run the planned tiny Ashr grading calibration batch when private evidence is available.
2. Replace offline LLM references with audited model-call evidence and cost/provenance metadata.
3. Expand the case book from one seed into a broader regression suite.

## 2026-07-04 - C4 semantic judge harness with dual SDK chains

Reason:
- Kay flagged that the official Ashr docs expose both Python and TypeScript SDK entrypoints.
- A2 already had C1 SDK parity, but C4 semantic/LLM judging also needed to keep the TypeScript chain visible instead of becoming Python-only.

Implemented:
- Added `services/judge/semantic_harness.py` to build deterministic `a2.semantic_harness.v1` evidence.
- Added generated fixture `fixtures/a2/results/a2_semantic_harness_report.json`.
- Added schema snapshot `docs/a2/schemas/semantic_harness.schema.json`.
- Integrated the semantic harness into `scripts/a2_regenerate_fixtures.py`.
- Updated the batch plan so `semantic_llm_judge_audit` names Python SDK, TypeScript SDK, local judge, and LLM judge sources together.
- Updated commercial readiness so C4 cites the semantic harness, while still staying partial because live model evidence is missing.
- Added tests for harness reproducibility, prompt/output/cost/redaction policy, media calibration coverage, and Python/TypeScript prompt paths.

Boundary:
- This pass does not call a live LLM and does not read `Ashr_key.txt`.
- The harness is ready for audited private model-call evidence, but `live_model_evidence_available` remains false until that evidence is collected and reviewed.

Next top 3:
1. Fill the `ashr_grading` column with reviewed Ashr server-side grading evidence.
2. Run the semantic harness with audited live model calls and commit only redacted summaries, hashes, costs, and confidence.
3. Expand the case book once real Ashr/LLM disagreements are available.

## 2026-07-04 - Semantic judge import bridge

Reason:
- The C4 harness defined what audited semantic judge evidence must look like, but A2 still needed a deterministic path for reviewed model-call summaries to enter the calibration matrix.
- The bridge should not require raw prompts, raw responses, API keys, or account-specific payloads in committed files.

Implemented:
- Added `import_semantic_judge_observations(...)` in `services/judge/calibration.py`.
- Added `scripts/a2_import_semantic_judge.py` to convert reviewed semantic judge summaries into `llm_judge` observations.
- Added `fixtures/a2/calibration/semantic_judge_import_sample.json` as a redaction/import shape sample only.
- Added tests proving semantic judge imports redact sensitive-looking rationale text, preserve provider/model/cost/hash/SDK language metadata, and can replace selected offline `llm_judge` rows through the existing merge gate.
- Updated A2 README, scenario coverage plan, and A1/A3 handoff docs.

Boundary:
- This does not mark C4 met and does not alter the committed calibration observations.
- The sample fixture is synthetic importer coverage, not live model evidence.

Next top 3:
1. Collect reviewed Ashr grading evidence for the six C3 cases.
2. Run the semantic harness privately and import all six reviewed `llm_judge` rows through the new bridge.
3. Promote any new cross-judge disagreements into the case book.

## 2026-07-04 - C5 regression replay report

Reason:
- The case book promoted one local-vs-LLM disagreement, but C5 also needs durable executable regression evidence.
- The batch plan already named `case_book_regression_replay`; A2 needed a generated artifact that proves replay actually happens.

Implemented:
- Added `services/judge/regression_replay.py` to re-run every case-book seed through deterministic `grade_run`.
- Added generated fixture `fixtures/a2/results/a2_regression_replay_report.json`.
- Added schema snapshot `docs/a2/schemas/regression_replay.schema.json`.
- Integrated replay generation into `scripts/a2_regenerate_fixtures.py`.
- Updated commercial readiness so C5 cites replay evidence and records `regression_replay_ready`, count, and maturity.
- Added tests proving the current `sample-a2-s010-wrong-arguments` seed still preserves local `wrong_arguments` while the LLM reference remains `ignored_tool_result`.

Boundary:
- C5 remains partial because the replay suite has one seed and `maturity_status: seed`.
- This does not alter `grade_run`, A3 grade joins, or calibration source semantics.

Next top 3:
1. Add more reviewed Ashr/local/LLM disagreement cases to the case book and replay suite.
2. Fill the `ashr_grading` column for the six calibration cases.
3. Replace offline `llm_judge` rows with audited semantic judge imports.

## 2026-07-04 - Official TypeScript chain made explicit

Reason:
- Kay flagged that the Ashr docs show one Python SDK route and one TypeScript SDK route.
- A2 already consumed TypeScript-shaped output, but the generated evidence needed to make the official `runAndDeploy` chain visible enough for reviewers.

Implemented:
- Added `official_sdk_chains` to the SDK parity report, mapping Python `EvalRunner.from_dataset(...)` / `run_and_deploy(...)` and TypeScript `EvalRunner.fromDataset(...)` / `runAndDeploy(...)` to A2-consumed shapes.
- Threaded that map into the semantic judge harness source matrix.
- Added tests that lock the TypeScript `npm install ashr-labs` and `CaseResult.agent_output` path.
- Updated A2 README and coverage planning docs.

Boundary:
- This is still deterministic A2 contract evidence.
- It does not claim hosted TypeScript API parity or run real Ashr grading.

Next top 3:
1. Keep the TypeScript chain green when A1/A3 update their TS package or report mapper.
2. Fill the `ashr_grading` column with reviewed server-side evidence.
3. Run audited semantic judge calls across both SDK chains and import reviewed summaries.

## 2026-07-04 - Media API calibration depth

Reason:
- Kay asked not to forget media-direction coverage.
- A2-S031 had media pipeline coverage, but the executable set did not explicitly include the common case where the agent calls the media API with the wrong classifier/configuration.

Implemented:
- Added `sample-a2-s031-media-pipeline-wrong-classifier-args` as an executable run fixture.
- Added `wrong_arguments` to A2-S031's documented failure signals.
- Extended the coverage report with executable media and tool-output-grounding calibration counts and case refs.
- Added tests that require the media executable set to cover pass, hallucinated tool result, wrong tool order, and wrong arguments.
- Updated A3's report builder summary to pass through the new media coverage fields.
- Updated README and scenario coverage docs.

Boundary:
- This does not add a new scenario; it strengthens executable calibration for the existing media/API scenario.
- It does not change `a2.grade_results.v1` or A3's grade join contract.

Next top 3:
1. Keep collecting real Ashr grading evidence for the six C3 calibration cases.
2. Run audited semantic judge calls for both Python and TypeScript SDK chains.
3. Add more media/audio/file scenarios only if the assignment/product target expands beyond the current 60-pack.

## 2026-07-04 - C3/C4 evidence readiness preflight

Reason:
- C3/C4 still need reviewed private Ashr grading and audited live semantic judge evidence.
- Before using any key or account payload, A2 should make the evidence collection contract explicit and testable.

Implemented:
- Added `services/judge/evidence_readiness.py` to generate `a2.evidence_readiness.v1`.
- Added generated fixture `fixtures/a2/results/a2_evidence_readiness_report.json`.
- Added schema snapshot `docs/a2/schemas/evidence_readiness.schema.json`.
- Integrated evidence readiness into `scripts/a2_regenerate_fixtures.py`.
- Updated commercial readiness so C3/C4 cite the evidence readiness artifact while staying partial.
- Added tests for case-map coverage, Ashr/semantic import commands, required semantic fields, SDK-language coverage, and private evidence boundaries.
- Updated README and scenario coverage docs.

Boundary:
- This does not call Ashr or a live LLM.
- It does not mark C3/C4 met; it only proves A2 is ready to collect and review the missing private evidence.

Next top 3:
1. Collect reviewed Ashr grading observations for all six calibration cases.
2. Replace offline `llm_judge` rows with audited semantic judge summaries.
3. Promote any new cross-judge disagreements into the case book and replay suite.

## 2026-07-04 - A3 evidence readiness summary

Reason:
- A2 now publishes an evidence-readiness preflight report, but A3 needed an optional display path for it.
- This keeps C3/C4 missing-evidence status visible to reviewers without changing the grade-result join.
- The official SDK surface is a parallel Python plus TypeScript matrix, so A3 evidence summaries should keep the TypeScript chain visible.

Implemented:
- Added `summarizeEvidenceReadiness(...)` to `services/report/report_builder.mjs`.
- Extended `buildJsonReport(...)` and `buildMarkdownReport(...)` with an optional fourth `evidenceReadinessFixture` argument.
- Added A3 tests that load `fixtures/a2/results/a2_evidence_readiness_report.json` and assert readiness status, Ashr missing count, SDK languages, and private evidence boundary.
- Updated A1/A3 handoff docs.

Boundary:
- This is optional A3 display support only.
- Existing three-argument report-builder calls remain valid.

Next top 3:
1. Use the readiness report when collecting reviewed Ashr grading evidence.
2. Import audited semantic judge summaries when available.
3. Keep A3 optional feeds additive so missing readiness artifacts never break core grade reports.
