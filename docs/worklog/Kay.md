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
