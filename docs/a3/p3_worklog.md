# P3 Worklog

## 2026-07-04

### Safety and Git state

- Ran `git fetch origin`; GitHub connection reset during the first check.
- Confirmed current branch: `codex/a3-p3-ashr-calibration`.
- Confirmed local HEAD equals the current local `origin/main`.
- Confirmed merged main includes A1, A2, and A3 merge commits.
- Confirmed `.env.local` exists.
- Confirmed `.env.local` is ignored by `.git/info/exclude`.
- Did not print or read the key value.

### Local contract reconnaissance

- Read A3 integration and fixture contracts:
  - `docs/a3/a3_integration_plan.md`
  - `docs/a3/mock_fixture_contract.md`
  - `services/report/report_builder.mjs`
- Read A1/A2 handoff:
  - `docs/a2/a1_a3_handoff.md`
- Read A1 schemas:
  - `docs/a1/schemas/run_result.schema.json`
  - `docs/a1/schemas/case_result.schema.json`
  - `docs/a1/schemas/agent_turn.schema.json`
  - `docs/a1/schemas/trace_event.schema.json`
  - `docs/a1/schemas/observation.schema.json`
- Read A2 grading schema:
  - `services/judge/schemas.py`
- Read A3 fixtures:
  - `fixtures/a3/mock_run_results.json`
  - `fixtures/a3/mock_grade_results.json`

### Real Ashr SDK reconnaissance

- Inspected local A1 PyPI artifact `ashr_labs-0.3.1`.
- Found `AshrLabsClient`, `RunBuilder`, `TestBuilder`, `Trace`, and typed models.
- Found production base URL in SDK artifact: `https://api.ashr.io/testing-platform-api`.
- Found SDK environment variable name: `ASHR_LABS_API_KEY`.
- Found user-provided project convention also mentions `ASHR_API_KEY`; P3 smoke code should support both without printing values.

### Current interpretation

- Real Ashr likely stores testing data as `Dataset` plus `Run`.
- A real `Run` has a nested `result`.
- A run result built by the SDK contains `tests[]`, `action_results[]`, and `aggregate_metrics`.
- Expected vs actual is represented by action results:
  - `expected` / `actual` for tool calls
  - `expected_response` / `actual_response` for text responses
- Trace-like production observability is a separate API concept with `Trace` and `observations[]`.

### Ashr smoke test results

- Safely loaded `.env.local` without printing the key.
- Used `ASHR_LABS_API_KEY` in the current process for the SDK.
- Imported the SDK from `docs/a1/_pypi_artifacts/ashr_labs-0.3.1-py3-none-any.whl`.
- Ran read-only calls:
  - `init()`: success.
  - `health_check()`: success.
  - `list_agents()`: success, empty list.
  - `list_datasets(limit=5, include_signed_urls=False)`: success.
  - `list_runs(limit=5)`: success.
  - `list_requests(limit=5)`: success.
  - `list_observability_traces(limit=5)`: failed; account feature flag `observability` is false.
- Saved sanitized fixtures:
  - `fixtures/a3/p3/ashr_auth_check.redacted.json`
  - `fixtures/a3/p3/ashr_field_sample.redacted.json`

### Mapper implementation

- Added `services/report/p3_ashr_mapper.mjs`.
- Added `tests/a3/p3_ashr_mapper.test.mjs`.
- The mapper converts `runs[].result.tests[].action_results[]` into:
  - A3 `runFixture.runs[].cases[]`
  - A3 `gradeFixture.grade_results[]`
  - expected vs actual panels
  - A1-like observations and trace events
  - derived failure classes for dashboard clustering

### Verification

- `node --test tests/a3/report_builder.test.mjs`: 4 tests passed.
- `node --test tests/a3/p3_ashr_mapper.test.mjs`: 4 tests passed.
- Confirmed `.env.local` remains ignored and untracked.

### Current blockers and assumptions

- GitHub `fetch` hit a network reset earlier, but local HEAD matches local `origin/main`.
- Observability API is not available for this account because `features.observability` is false.
- Native backend failure-class fields were not visible in the current successful run sample.
- P3 mapper currently derives `primary_failure_class` from `match_status`, tool-call comparison, and response divergence.

### Next top 3

1. Get or create one minimal failing run so P3 can verify native failure fields, if any.
2. Decide whether A3 should display `semantic_similarity` as score or wait for a stronger server grade.
3. Join `list_runs()` data with `list_datasets()` data so case titles can come from `dataset_source.runs.*.title`.

### Completed commands

- `git fetch origin`
- `git status -sb`
- `git branch --show-current`
- `git rev-list --left-right --count HEAD...origin/main`
- `git check-ignore -v .env.local`
- `rg --files docs/a1 docs/a2 docs/a3 packages/sdk packages/scenarios services/runner services/judge services/report fixtures`
- `tar -tf docs/a1/_pypi_artifacts/ashr_labs-0.3.1.tar.gz`
- `python -m zipfile -l docs/a1/_pypi_artifacts/ashr_labs-0.3.1-py3-none-any.whl`
- Read-only Ashr SDK smoke test via `AshrLabsClient`.
- `node --test tests/a3/report_builder.test.mjs`
- `node --test tests/a3/p3_ashr_mapper.test.mjs`

## 2026-07-04 - Product Console / Media Evidence iteration

### Baseline and peer state

- Current branch: `codex/a3-p3-ashr-calibration`.
- `.env.local` is ignored by `.git/info/exclude`.
- `gh pr list --state all --limit 20` showed:
  - PR #5 `P3 Ashr calibration for A3 dashboard`: merged.
  - PR #6 `A1 local SDK runner, cloud API, and TS quickstart`: merged.
  - PR #7 `A1 queue worker and TS API client parity`: open draft.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` failed with a network reset. This is recorded as merge risk because local `origin/main` may be stale even though GitHub API was reachable.

### ROI decision

Selected `Media Evidence` for this round.

Reason:

- Real Ashr samples already exposed media fields that A3 could not display.
- Media evidence has high demo value because non-developers can understand audio/file/VM evidence faster than raw JSON.
- Supporting media fields reduces integration risk for future real Ashr data.

Backlog:

- Trace tree + tool-call diff + judge drilldown.
- Report center with more formal export workflow.
- Authenticated official Ashr dashboard observation after manual login.

### Real Ashr media calibration

Read-only Ashr API/SDK evidence from this round is saved in sanitized files:

- `fixtures/a3/p3/ashr_media_field_sample.redacted.json`
- `fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_run_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`

Confirmed fields:

- `dataset_source.runs.*.actions[]`
- `action_type`: `text`, `file`, `audio`
- `action_tags`
- `output_path`
- `expected_response.tool_calls`
- `run.result.cases[]`
- `case.metadata.action_type`
- `case.metadata.audio_tags`
- `case.metadata.intent_tags`
- `case.observations[].vm_stream`
- `grade.expected`
- `grade.actual`
- `grade.metrics`
- `grade.passed`
- `grade.score`

### Official frontend observation

- Public site observed at `https://ashr.io/`.
- Public product concepts seen: datasets, test details, explore, prompts, SDK, full test timelines, expected vs actual, usage scaling.
- Lab frontend opened at `https://lab.ashr.io/` and landed on sign-in/onboarding.
- No login, form submission, workspace creation, or plan selection was performed.
- Notes saved in `docs/a3/p3_official_frontend_notes.md`.

### Implemented

- Extended `services/report/p3_ashr_mapper.mjs` to support:
  - `run.result.tests[].action_results[]`
  - `run.result.cases[]`
  - media evidence summary
  - audio/file/image/video action types
  - action tags and output paths
  - VM stream summaries
  - media timeline events such as `media.vm_stream`
- Extended `services/report/report_builder.mjs` to include media evidence counts in summaries and media fields in JSON/CSV exports.
- Extended `tests/a3/p3_ashr_mapper.test.mjs` with a real redacted `result.cases[]` media sample test.
- Updated `apps/dashboard/index.html` into a product-console style UI:
  - data source switcher
  - product console overview
  - Usage / Quota known-gap panel
  - Requests / datasets / runs object summary
  - Media Evidence panel in Case Detail
  - P3 media sample view powered by the mapper

### Screenshots

- `docs/screenshots/a3-p3-product-console-media-overview.png`
- `docs/screenshots/a3-p3-product-console-media-mobile.png`

### Verification

- `node --test tests/a3/report_builder.test.mjs`: 4 tests passed.
- `node --test tests/a3/p3_ashr_mapper.test.mjs`: 5 tests passed.
- Browser smoke: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Browser checks:
  - Page title rendered `A3 Product Console`.
  - Data source rendered `P3 redacted Ashr media sample`.
  - Case rows: 3.
  - Media Evidence metric: 3.
  - Media panel showed `audio` and `vm_stream`.
  - Console logs: no warnings/errors.
  - Mobile viewport width 390 had no horizontal overflow.

### Next top 3

1. Add a trace/tool-call diff panel for expected vs actual tool-call comparison.
2. Add a report-center page with saved report history and PDF-ready layout.
3. After a teammate logs into Ashr Lab, observe authenticated requests/datasets/runs/detail pages and update `p3_official_frontend_notes.md`.
