# A3 Worklog

## 2026-07-04 - First A3 pass

### Goal

Start A3 Dashboard & Triage work after A1/A2 opened draft PRs. Do not merge A1/A2. Read their contracts and create an independent dashboard skeleton that can consume A1/A2-style fixtures.

### Commands

```text
gh repo clone 3351666087/ashr-codex-factory ashr-codex-factory
git fetch origin
git status -sb
gh pr list --repo 3351666087/ashr-codex-factory --state open --json number,title,headRefName,baseRefName,isDraft,author,updatedAt,url
git diff --name-status origin/main...origin/codex/a1-local-sdk-runner
git diff --name-status origin/main...origin/dev/a2-scenario-judge
gh pr view 1 --repo 3351666087/ashr-codex-factory --json title,body,files,commits,reviews,comments
gh pr view 2 --repo 3351666087/ashr-codex-factory --json title,body,files,commits,reviews,comments
git switch -c codex/a3-dashboard-triage
node --test tests/a3/report_builder.test.mjs
python -m http.server 5173 --bind 127.0.0.1
```

### PR reconnaissance

- PR #1: `A1 local SDK runner trace loop`, draft, branch `codex/a1-local-sdk-runner`.
- PR #2: `A2: Scenario and judge foundation`, draft, branch `dev/a2-scenario-judge`.
- Main branch has only `README.md`, so A3 cannot directly import merged A1/A2 files yet.

### Implemented

- Added A3 mock run fixture based on A1/A2 field names.
- Added A3 mock grade fixture based on A2 grade output.
- Added pure report builder functions in `services/report/report_builder.mjs`.
- Added static dashboard skeleton in `apps/dashboard/index.html`.
- Added A3 tests for summary, clustering, and exports.
- Added A3 integration plan, mock fixture contract, and acceptance checklist.
- Verified the dashboard in browser at `http://127.0.0.1:5173/apps/dashboard/index.html`.
- Captured desktop, failed case, failure cluster, and mobile viewport screenshots.
- Added 6 dashboard filters: status, scenario family, failure class, run, severity, and score band.
- Added selected-case judge drilldown below Expected vs Actual.
- Added report-builder filter helpers so filtering can be tested outside the UI.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

Browser checks:

- Summary rendered `Runs=1`, `Cases=4`, `Pass Rate=50%`, `Trace Complete=100%`.
- Failure clusters rendered `missing_required_tool` and `wrong_arguments`.
- Failed case detail for `A2-S004` showed expected `web.search` and actual empty `tool_calls`.
- Mobile viewport rendered single-column layout at width 390.
- Filter logic covers failed + major + 70-89 score band.
- Captured 10 demo screenshots covering summary, failed detail, clusters, filters, wrong argument detail, judge drilldown, export actions, and mobile viewport.

### Evidence paths

- `docs/a3/a3_integration_plan.md`
- `docs/a3/mock_fixture_contract.md`
- `docs/a3/acceptance_checklist.md`
- `fixtures/a3/mock_run_results.json`
- `fixtures/a3/mock_grade_results.json`
- `apps/dashboard/index.html`
- `services/report/report_builder.mjs`
- `tests/a3/report_builder.test.mjs`
- `docs/screenshots/a3-dashboard-summary.png`
- `docs/screenshots/a3-dashboard-case-detail.png`
- `docs/screenshots/a3-dashboard-failure-clusters.png`
- `docs/screenshots/a3-dashboard-mobile-viewport.png`
- `docs/screenshots/a3-01-summary.png`
- `docs/screenshots/a3-02-failed-case-detail.png`
- `docs/screenshots/a3-03-failure-clusters.png`
- `docs/screenshots/a3-04-filter-failed.png`
- `docs/screenshots/a3-05-filter-major.png`
- `docs/screenshots/a3-06-filter-score-band.png`
- `docs/screenshots/a3-07-wrong-argument-detail.png`
- `docs/screenshots/a3-08-judge-drilldown.png`
- `docs/screenshots/a3-09-export-actions.png`
- `docs/screenshots/a3-10-mobile-viewport.png`

### Known gaps

- A1/A2 draft PR files are not merged into main, so A3 uses mock fixtures for now.
- Root package/test configuration does not exist yet; A3 tests use Node's built-in test runner directly.

### Next top 3

1. Add judge-mode filter after A2 has more varied sample judge modes.
2. Create a transform script after A1/A2 PRs merge so A3 can replace mock fixtures with real outputs.
3. Replace the static HTML shell with the team's final frontend stack if the repo standardizes on one.

## 2026-07-04 - P3 Ashr calibration

### Goal

Start P3/G3 real Ashr calibration after A1, A2, and A3 merged into main. Keep the work small and safe: verify key hygiene, inspect real Ashr field shapes, save redacted evidence, and add only a narrow mapper for A3.

### Implemented

- Added `docs/a3/p3_ashr_calibration_plan.md`.
- Added `docs/a3/p3_field_mapping.md`.
- Added `docs/a3/p3_worklog.md`.
- Saved redacted Ashr smoke fixtures under `fixtures/a3/p3`.
- Added `services/report/p3_ashr_mapper.mjs`.
- Added `tests/a3/p3_ashr_mapper.test.mjs`.
- Updated `docs/a3/acceptance_checklist.md`.

### Smoke test summary

- `.env.local` exists and is ignored by Git.
- The key was read only through environment variables and was not printed.
- `init()`, `health_check()`, `list_datasets()`, `list_runs()`, and `list_requests()` succeeded.
- `list_agents()` succeeded but returned an empty list.
- `list_observability_traces()` failed because this account has `features.observability == false`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 8
pass 8
fail 0
```

### Next top 3

1. Verify native backend failure-class fields with a real failing Ashr run.
2. Decide whether A3 should display `semantic_similarity` as the score or wait for a stronger server grade field.
3. Join `list_runs()` with `list_datasets()` so A3 cases can use real scenario titles.

## 2026-07-04 - Product console media evidence iteration

### Goal

Continue A3 after P3 calibration and move the dashboard toward a commercial-grade product console. This round chose one highest ROI enhancement: media evidence calibration and display.

### Implemented

- Added `docs/a3/p3_media_calibration.md`.
- Added `docs/a3/p3_official_frontend_notes.md`.
- Extended `services/report/p3_ashr_mapper.mjs` to support real Ashr `run.result.cases[]` samples.
- Added `media_evidence` mapping for media type, action tags, output paths, audio tags, intent tags, VM stream summaries, and known gaps.
- Added media timeline events such as `media.vm_stream`.
- Extended `services/report/report_builder.mjs` so summary/export includes media evidence.
- Added P3 media sample coverage in `tests/a3/p3_ashr_mapper.test.mjs`.
- Updated `apps/dashboard/index.html` from a demo dashboard toward a product console:
  - data source switcher
  - workflow overview
  - Usage / Quota known-gap panel
  - Requests / datasets / runs object summary
  - case-level Media Evidence panel
  - P3 media sample mode

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 9
pass 9
fail 0
```

Browser checks:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed title, P3 data source, 3 case rows, 3 media-evidence cases, and Media Evidence panel.
- Confirmed no browser console warnings/errors.
- Confirmed mobile viewport width 390 has no horizontal overflow.

### Evidence paths

- `fixtures/a3/p3/ashr_media_field_sample.redacted.json`
- `fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_run_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`
- `docs/a3/p3_media_calibration.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/screenshots/a3-p3-product-console-media-overview.png`
- `docs/screenshots/a3-p3-product-console-media-mobile.png`

### Known gaps

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` failed with a network reset, so local remote refs may lag GitHub API state.
- Authenticated `lab.ashr.io` dashboard observation is blocked until a logged-in session is available.
- Real signed media URLs for audio/image/video are not confirmed in the sanitized sample.
- Native Ashr backend failure-class fields remain unconfirmed; A3 still derives failure class for the media sample.

### Next top 3

1. Add trace/tool-call expected-vs-actual diff.
2. Add report center / PDF-ready report layout.
3. Observe authenticated Ashr Lab after manual login and update A3 navigation assumptions.

## 2026-07-04 - Tool-call diff follow-up

### Goal

Continue the next A3 backlog item: make tool-call failures directly readable in the dashboard and exported JSON.

### Implemented

- Added `buildToolCallDiffs(caseResult)` to `services/report/report_builder.mjs`.
- Added `tool_call_diffs` to JSON export.
- Added test coverage in `tests/a3/report_builder.test.mjs`.
- Added dashboard `Tool Call Diff` panel under Case Detail.
- Added `docs/a3/p3_tool_call_diff.md`.
- Captured `docs/screenshots/a3-p3-tool-call-diff.png`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 10
pass 10
fail 0
```

Browser checks:

- Missing required tool case showed `missing_required_tool`.
- Wrong argument case showed `wrong_arguments`.
- Tool name and argument JSON rendered in expected/actual columns.
- Desktop check showed no horizontal overflow.

### Next top 3

1. Add field-level argument highlighting.
2. Add report center / PDF-ready report layout.
3. Observe authenticated Ashr Lab after manual login.

## 2026-07-04 - Dashboard product-console polish

### Goal

Continue optimizing A3's third part by making the dashboard feel more like a commercial product console while preserving the existing local fixture workflow.

### Implemented

- Added `docs/a3/a3_dashboard_polish.md`.
- Refined dashboard visual styling with clearer panel spacing, shadows, and health color accents.
- Added `Coverage Health` to surface A2 coverage summary, assignment health, and coverage warnings.
- Added `Triage Queue` to rank current failed cases by severity and score.
- Added `Report Center` to explain JSON/CSV/Markdown report contents and mirror export actions.
- Shared one export handler across topbar export buttons and Report Center buttons.
- Added dashboard wiring test coverage for the new product-console panels.
- Escaped rendered judge, trace, and cluster text for safer fixture rendering.
- Added P3 mapper de-duplication for repeated redacted case IDs so dashboard selection is deterministic.
- Captured desktop, P3 media, and mobile screenshots for this polish pass.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 19
pass 19
fail 0
```

Browser checks:

- Mock dashboard rendered Coverage Health, Triage Queue, and Report Center.
- P3 media dashboard rendered 3 cases, 3 media-evidence cases, and exactly one active triage row after P3 case ID de-duplication.
- Mobile viewport width 390 had no horizontal overflow.
- Browser console warnings/errors: none.

### Evidence paths

- `docs/a3/a3_dashboard_polish.md`
- `docs/screenshots/a3-dashboard-polish-overview.png`
- `docs/screenshots/a3-dashboard-polish-p3-media.png`
- `docs/screenshots/a3-dashboard-polish-mobile.png`

### Next top 3

1. Add field-level tool argument diff highlighting.
2. Link each tool diff row back to A2 judge evidence.
3. Add a print/PDF-ready report layout if the team wants handoff docs directly from A3.

## 2026-07-04 - Field-level argument diff follow-up

### Goal

Make `wrong_arguments` failures easier to understand by showing exactly which tool argument field changed, went missing, or appeared unexpectedly.

### Implemented

- Added `buildArgumentDiffs()` in `services/report/report_builder.mjs`.
- Extended `buildToolCallDiffs()` so each diff row can include `argument_diffs`.
- Preserved `argument_diffs` in JSON report export through the existing `tool_call_diffs` field.
- Updated the dashboard `Tool Call Diff` panel to show argument path, status, expected value, and actual value.
- Added test coverage for changed, missing, and unexpected argument fields.
- Updated `docs/a3/p3_tool_call_diff.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 21
pass 21
fail 0
```

Browser checks:

- Selected the `Wrong Argument Trap` case in the dashboard.
- Confirmed `argument_diffs` rendered one field row for `path`.
- Confirmed status `changed_argument`.
- Confirmed expected value `fixtures/a2/contracts/vendor-alpha.txt`.
- Confirmed actual value `fixtures/a2/contracts/vendor-alfa.txt`.
- Desktop viewport had no horizontal overflow.
- Browser console warnings/errors: none.

### Evidence paths

- `docs/screenshots/a3-dashboard-argument-diff.png`

### Next top 3

1. Link each diff row back to A2 judge evidence.
2. Add a print/PDF-ready report layout if the team wants handoff docs directly from A3.
3. Add semantic matching for reordered tool calls instead of index-only matching.

## 2026-07-04 - Tool diff judge evidence linkage

### Goal

Connect each A3 `Tool Call Diff` row back to the A2 judge evidence that explains why the row failed.

### Implemented

- Added `judge_evidence` to each `buildToolCallDiffs()` row when a failed A2 judge result matches the diff failure class or tool call ID.
- Preserved judge evidence in JSON export through the existing `tool_call_diffs` field.
- Dashboard now renders judge mode, score, failure class, severity, summary, tool evidence IDs, details, and remediation under the relevant tool diff row.
- Added report-builder test coverage for missing-tool and wrong-argument judge evidence linkage.
- Added dashboard wiring test coverage for the judge evidence UI.
- Updated `docs/a3/p3_tool_call_diff.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 22
pass 22
fail 0
```

Browser checks:

- Selected the `Wrong Argument Trap` case in the dashboard.
- Confirmed the matching diff row renders `g1_trace_contract_judge`.
- Confirmed tool evidence ID `file.read#1`.
- Confirmed judge details and remediation render under the tool diff.
- Desktop viewport had no horizontal overflow.
- Browser console warnings/errors: none.

### Evidence paths

- `docs/screenshots/a3-dashboard-judge-evidence.png`

### Next top 3

1. Add a print/PDF-ready report layout if the team wants handoff docs directly from A3.
2. Add semantic matching for reordered tool calls instead of index-only matching.
3. Deep-link judge evidence to exact trace event IDs when shared trace IDs are available.

## 2026-07-04 - Print-ready report preview

### Goal

Add a PDF-ready report view so A3 can produce a handoff report directly from the dashboard, not only through JSON/CSV/Markdown downloads.

### Implemented

- Added dashboard `Report Preview` section.
- Added `Print Report` topbar action and `Print/PDF` Report Center action.
- Added print CSS that hides sidebar, filters, operational controls, run list, and case detail during browser print.
- Added `renderPrintReport()` to summarize metrics, coverage health, failure clusters, triage queue, selected case evidence, tool diffs, and linked judge evidence.
- Updated Report Center to describe the Print/PDF workflow.
- Added dashboard wiring test coverage for the report preview and print path.
- Updated `docs/a3/a3_dashboard_polish.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 23
pass 23
fail 0
```

Browser checks:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html#report-preview`.
- Confirmed Report Preview renders summary metrics, coverage health, failure clusters, triage queue, selected case evidence, tool diff, and linked judge evidence.
- Selected the `Wrong Argument Trap` failed case and confirmed the report preview refreshed to show `wrong_arguments` evidence.
- Confirmed no horizontal overflow at desktop viewport width.
- Browser console warnings/errors: none.

Evidence path:

- `docs/screenshots/a3-dashboard-print-report.png`

### Next top 3

1. Add semantic matching for reordered tool calls instead of index-only matching.
2. Deep-link judge evidence to exact trace event IDs when shared trace IDs are available.
3. Add judge-mode filtering after A2 exposes more varied judge-mode samples.

## 2026-07-04 - Semantic tool-call matching closeout

### Goal

Stop expanding A3 and close one remaining high-value Tool Call Diff gap: reordered tool calls should be shown as `wrong_tool_order`, not as unrelated `wrong_tool` rows.

### Implemented

- Updated `buildToolCallDiffs()` to pair expected and actual tool calls by semantic similarity before falling back to index matching.
- Added diff metadata: `match_strategy`, `expected_index`, `actual_index`, and `order_changed`.
- Added `wrong_tool_order` diff status when the same tool and arguments appear in a different position.
- Updated judge evidence matching so reordered rows can still link back to A2 `tool_call_ids`.
- Added dashboard display for matching strategy and original expected/actual positions.
- Added one A3 mock `wrong_tool_order` case so the dashboard can demonstrate the behavior.
- Added report-builder and dashboard wiring tests.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 25
pass 25
fail 0
```

Spot check:

- `sample-a2-s009-wrong-order` now produces two `wrong_tool_order` rows.
- Both rows use `semantic_exact_reordered`.
- Expected `web.search` matches actual `web.search` even when actual position is #2.
- Expected `web.open` matches actual `web.open` even when actual position is #1.
- Both rows keep linked A2 judge evidence.

### Stop point

This is a reasonable A3 polish stopping point. Remaining items are optional refinements, not required for the current dashboard/report handoff.

## 2026-07-05 - Judge-mode filter closeout

### Goal

Continue yesterday's unfinished A3 acceptance work without expanding scope. The clear remaining UI gap was that `services/report/report_builder.mjs` already exposed `judgeModes` and `filterCases(..., { judgeMode })`, but the dashboard did not yet have a Judge Mode filter control.

### Implemented

- Added a `Judge Mode` select to the dashboard filter row.
- Populated the select from normalized A2 judge modes through `getFilterOptions(state.cases).judgeModes`.
- Wired the selected judge mode into `filterCases()`.
- Added dashboard wiring test coverage.
- Extended report-builder filter tests to verify `g1_trace_contract_judge` and `g2_output_contract_judge` options and judge-mode filtering behavior.
- Updated `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 26
pass 26
fail 0
```

Spot check:

- Judge mode options include `g1_trace_contract_judge` and `g2_output_contract_judge`.
- Filtering by `g2_output_contract_judge` returns `sample-a2-s001-pass` and `sample-a2-s004-missing-tool`.

### Scope safety

- No real Ashr API calls.
- No secret/key reads or writes.
- No A1 runner logic changes.
- No A2 judge semantic changes.

## 2026-07-05 - Dataset scenario title join closeout

### Goal

Continue the remaining P3 A3 mapper acceptance item without using real credentials or expanding scope: mapped A3 cases should be able to use scenario titles from Ashr dataset samples instead of falling back only to test/case IDs.

### Implemented

- Added `buildDatasetScenarioIndex()` in `services/report/p3_ashr_mapper.mjs`.
- Added optional `datasetSample` support to `mapAshrSampleToA3Fixtures()`.
- Joined dataset scenario title, dataset type, scenario key, and intent tags into mapped A3 cases when a dataset sample is provided.
- Kept fallback behavior unchanged when no dataset sample is available.
- Updated P3 media dashboard loading so it passes `ashr_dataset_detail_sample.redacted.json` into the mapper.
- Added mapper test coverage for dataset title joins.
- Added dashboard wiring test coverage to ensure the P3 dataset sample is passed into the mapper.
- Updated `docs/a3/acceptance_checklist.md` and `docs/a3/p3_field_mapping.md`.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs
```

Result:

```text
tests 28
pass 28
fail 0
```

Spot check:

- P3 media sample mapping reports `metadata.dataset_scenario_joined=true`.
- Mapped cases preserve joined dataset scenario titles in `metadata.dataset_scenario_title`.
- No real Ashr API calls were made; only committed redacted fixtures were used.

### Remaining P3 unknowns

- Native Ashr backend failure-class evidence was checked later with a real failed run; current sample has no named backend `failure_class`.
- Signed media URL fields still need confirmation from an unsanitized or richer sample.
- Authenticated Ashr Lab UI observation still requires a manual logged-in browser session.

## 2026-07-05 - Judge evidence trace-link closeout

### Goal

Close the remaining A3 Tool Call Diff evidence item without using live Ashr data: judge evidence should point back to matching trace event IDs when A3 has trace events with matching tool names or tool call IDs.

### Implemented

- Added `trace_event_links` to each A3 tool-call diff row.
- Added linked `evidence.trace_event_ids` inside each matching `judge_evidence` block.
- Matched trace events by tool name and tool call ID.
- Preserved fallback trace IDs when the source event lacks a stable `event_id`.
- Updated dashboard Judge Evidence rendering to show `Trace events`.
- Updated print/report preview judge evidence text to include trace event IDs.
- Added report-builder and dashboard wiring tests.
- Updated `docs/a3/acceptance_checklist.md` and `docs/a3/p3_tool_call_diff.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 28
pass 28
fail 0
```

Spot check:

- `sample-a2-s010-wrong-argument` now links `file.read` judge evidence to `sample-a2-s010-wrong-argument:trace:1`.
- Reordered tool-call tests link `web.search` and `web.open` to their exact synthetic trace event IDs.

### Stop point

This is the chosen stop point for this run. Remaining unchecked items need live/less-sanitized Ashr evidence or manual authenticated UI access, so they should not be forced in this local-only A3 pass.

## 2026-07-05 - Score source policy closeout

### Goal

Close the P3 score-source decision without live API calls. A3 needed a clear rule for whether dashboard/report scores come from `semantic_similarity` or from stronger Ashr grade fields.

### Decision

A3 now uses this priority:

1. `case.grade.score` when present, recorded as `ashr_case_grade_score`.
2. `case.score` when present, recorded as `ashr_case_score`.
3. Average `action_results[].semantic_similarity` for action-results samples without a stronger grade, recorded as `semantic_similarity_average`.
4. Pass/fail fallback only when no score-like field exists, recorded as `pass_fail_default`.

### Implemented

- Added `score_source` and `score_source_detail` metadata in P3 mapped cases.
- Added grade-result metadata with the same score source.
- Added `score_source` to A3 JSON report export.
- Added mapper and report-builder tests for score-source behavior.
- Updated `docs/a3/acceptance_checklist.md` and `docs/a3/p3_field_mapping.md`.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 28
pass 28
fail 0
```

Spot check:

- Action-results sample uses `semantic_similarity_average`.
- P3 media case-result sample uses `ashr_case_grade_score`.
- Mock A3 cases export `score_source=unknown`, because they predate P3 score provenance.

### Stop point

This is a reasonable local-only stop point. Remaining P3 evidence items require live failing Ashr runs, signed media URL confirmation, or authenticated Ashr Lab access.

## 2026-07-05 - Generated A3 fixture closeout

### Goal

Close the remaining local-only A3 acceptance item: replace hand-maintained A3 mock fixtures with reproducible fixtures generated from merged A2 outputs.

### Implemented

- Added `services/report/a3_fixture_builder.mjs`.
- The builder reads:
  - `packages/scenarios/a2_g3_full_pack.json`
  - `fixtures/a2/results/a2_g3_grade_results.json`
  - `fixtures/a2/runs/*.json`
- Regenerated:
  - `fixtures/a3/mock_run_results.json`
  - `fixtures/a3/mock_grade_results.json`
- The default A3 mock dashboard now uses 32 merged A2 executable cases instead of 5 hand-maintained demo cases.
- Preserved A2 judge results, scenario titles, scenario families, expected tool calls, actual tool calls, final responses, observations, and trace events.
- Added special handling for `wrong_tool_order` cases where A2 declares tool names but omits expected args, so A3 shows order diffs instead of false argument diffs.
- Added `tests/a3/a3_fixture_builder.test.mjs` to prove the checked-in A3 fixtures match the generated output.
- Updated `tests/a3/report_builder.test.mjs` for the 32-case generated fixture.
- Updated `docs/a3/mock_fixture_contract.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node services/report/a3_fixture_builder.mjs --write
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 30
pass 30
fail 0
```

### Stop point

This is a clean local stop point. The remaining unchecked items require external/manual evidence: a real failing Ashr run, authenticated Ashr Lab UI observation, or richer signed media URL samples.

## 2026-07-05 - Frontend/API product logic calibration

### Goal

Continue P3 by using the now-local `ASHR_API_KEY` safely, collecting real Ashr API field evidence, and documenting how real Ashr frontend/product logic maps into the A3 Dashboard / Triage / Report MVP.

### Implemented

- Confirmed `.env.local` remains ignored and contains one `ASHR_API_KEY` entry without printing the key.
- Ran a read-only real Ashr API calibration using the key from environment only.
- Saved new sanitized fixtures:
  - `fixtures/a3/p3/ashr_frontend_api_objects.redacted.json`
  - `fixtures/a3/p3/ashr_run_trace_sample.redacted.json`
  - `fixtures/a3/p3/ashr_media_url_sample.redacted.json`
- Confirmed successful read-only calls for:
  - `init`
  - `health_check`
  - `list_agents`
  - `list_datasets`
  - `get_dataset`
  - `list_runs`
  - `get_run`
  - `list_requests`
  - `get_request`
  - signed-url dataset probes
- `list_observability_traces` still failed because the account does not have observability enabled.
- Confirmed `get_run` can return a direct run object with `result.cases[]`.
- Confirmed the redacted run sample contains expected/actual, score, pass/fail, failure-like fields, and tool-call evidence.
- Confirmed a signed media/file URL field name: `actions[].signed_url`; the value is redacted.
- Added frontend/product docs:
  - `docs/a3/p3_frontend_page_map.md`
  - `docs/a3/p3_frontend_workflow_notes.md`
  - `docs/a3/p3_frontend_field_mapping.md`
  - `docs/a3/p3_frontend_to_a3_mvp_gap.md`
  - `docs/a3/p3_a3_mvp_recommendations.md`
- Updated `docs/a3/p3_field_mapping.md`, `docs/a3/p3_official_frontend_notes.md`, and `docs/a3/acceptance_checklist.md`.

### Frontend observation result

- A Windows Edge window titled `Ashr Labs ... Microsoft Edge` was present.
- Direct content extraction from that logged-in Edge window was stopped by the browser-control safety layer because it could not verify the current browser URL.
- Codex in-app browser was available but did not share the Edge login state.
- No logged-in screenshots were saved and no UI state was changed.

### Verification target

Run the A3 test suite and secret scan after this documentation pass.

### Next top 3

1. Log into Ashr Lab inside the Codex in-app browser or provide sanitized screenshots so A3 can directly confirm page labels and navigation.
2. Add a small request provenance panel in A3 using the confirmed `request_status`, duration, accepted-input, and generation-option fields.
3. Get one UI-visible populated hosted run to verify frontend run/case detail pages and frontend failure labels.

## 2026-07-06 - Authenticated Ashr Lab UI calibration

### Goal

Finish the direct authenticated frontend observation that was blocked in the prior round.

### What happened

- The user could not log into Ashr through the Codex in-app browser because Google OAuth returned `400 Bad Request`.
- Normal Edge/Chrome windows still could not be inspected safely because browser URL verification failed.
- Opened a separate Chrome profile with local CDP debugging on port `9222`.
- The user manually logged into Ashr in that isolated Chrome profile.
- Used read-only CDP/Playwright observation after login.

### Confirmed UI pages

- Datasets: `?tab=analysis`
- Agents: `?tab=agents`
- Folders: `?tab=folders`
- Analytics: `?tab=analytics`
- Usage: `?tab=usage`
- Trust: `?tab=trust`
- API Keys: `?tab=api-keys`
- Team: `?tab=team`

### Confirmed product logic

- Datasets page has search, filters, sort, group, pinned-only, and `New dataset`.
- New Dataset is an 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.
- Analytics exposes run volume, pass rate over time, runs by agent, and pass rate by agent.
- Usage tracks Images, Audio, and Files quota.
- Trust is a public certificate/trust-page concept with frozen metrics.
- API Keys and Team are real admin pages but outside A3 MVP scope.

### Updated docs

- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_workflow_notes.md`
- `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- `docs/a3/p3_frontend_field_mapping.md`
- `docs/a3/p3_a3_mvp_recommendations.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/a3/p3_worklog.md`
- `docs/a3/acceptance_checklist.md`

### Safety

- No screenshots saved from the authenticated account.
- No cookies, tokens, key values, or account-specific values saved.
- No create/delete/submit actions performed.
- `.env.local` was not touched.

### Verification

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 30
pass 30
fail 0
```

Additional checks:

- `git diff --check`: only LF-to-CRLF warnings.
- `.env.local`: ignored by `.gitignore`.
- Targeted secret scans: no account email, username, real API-key assignment, bearer token, cookie assignment, or token assignment found in the new authenticated-frontend docs.
- Broader A3 scan still matches an intentional fake fixture string shaped like `ashr_live_...`; this is synthetic test content and not a real secret.

### Remaining gaps

- Need a populated Ashr hosted run to observe run detail, case detail, trace/timeline, expected-vs-actual, and frontend failure labels.
- Need a UI-visible populated hosted run to verify frontend failure labels; backend failed-run fields were checked later through the API.

## 2026-07-06 - Request Provenance panel

### Goal

Use the already-confirmed Ashr request API fields to improve A3's product-console workflow without making live API calls.

### Implemented

- Added `summarizeRequestProvenance()` to `services/report/report_builder.mjs`.
- Added request provenance to JSON and Markdown exports.
- Added dashboard `Request Provenance` panel.
- Dashboard P3 media source now loads `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`.
- Added tests for report-builder request summary and dashboard wiring.
- Updated A3/P3 docs and acceptance checklist.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 32
pass 32
fail 0
```

Browser smoke:

- Local preview: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`
- Request Provenance rendered status, accepted inputs, generation outputs, tool count, strategy, and failure flag.
- Browser console warnings/errors: none.
- Screenshot: `docs/screenshots/a3-dashboard-request-provenance.png`

### Scope safety

- No live Ashr API calls.
- No `.env.local` access.
- No A1 runner logic changes.
- No A2 judge semantic changes.
- Only A3-owned code/docs were changed.

### Remaining gaps

- Native backend failure-class evidence has now been checked with a real failed run; frontend failure labels still need a UI-visible populated run.
- Populated Ashr run/case/trace frontend pages still need a non-empty Lab account or generated sample.
- Full signed media URL rendering is still blocked until per-modality redaction/access behavior is confirmed.

## 2026-07-06 - Real failed-run API probe

### Goal

Continue P3 calibration with the user's logged-in Chrome session and local `.env.local` key, while keeping the work read-only and secret-safe.

### API evidence

- Ran read-only `list-runs` and `list-requests` probes.
- Found a real failed run in the Ashr API response.
- Saved sanitized fixtures:
  - `fixtures/a3/p3/ashr_failed_run_probe.redacted.json`
  - `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`
  - `fixtures/a3/p3/ashr_request_probe.redacted.json`
  - `fixtures/a3/p3/ashr_failed_request_detail.redacted.json`
- Confirmed failed-run fields:
  - `run.result.status`
  - aggregate passed/failed counts
  - `run.result.cases[]`
  - per-case `status`
  - `grade.label`
  - `grade.passed`
  - `grade.score`
  - `grade.reason`
  - `grade.metrics`
- Confirmed no named native backend `failure_class` field in this failed-run sample.
- A3 therefore still derives failure clusters from grade metrics and expected/actual evidence.

### Frontend evidence

- Connected read-only to the user's logged-in Chrome through local CDP.
- Confirmed the Lab Datasets page loaded but showed 0 UI-visible datasets.
- Confirmed Analytics loaded but showed 0 agents, 0 datasets, 0 graded runs, and not enough data.
- Confirmed Trust, Agents, and Folders empty states.
- Did not save authenticated screenshots or account-specific values.

### Implemented

- Updated `services/report/p3_ashr_mapper.mjs` so `extractAshrRuns()` accepts API probe wrapper shapes such as `response.run` and `response.runs`.
- Added mapper test coverage for the real redacted failed-run fixture.
- Updated P3 field mapping, frontend gap docs, MVP recommendations, and acceptance checklist.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 33
pass 33
fail 0
```

### Remaining gaps

- Need one UI-visible populated Lab run to observe real frontend run detail, case detail, expected-vs-actual, tool calls, trace/timeline, and frontend failure labels.
- Need per-modality signed media URL behavior before rendering live signed links.
- Keep failure class derived unless a future Ashr sample exposes a named backend `failure_class`.

## 2026-07-06 - API/frontend visibility gap documented

### Goal

Explain why the authenticated Lab frontend can show empty states while the API still returns populated calibration objects.

### Evidence

- Ran read-only API probes for datasets, runs, requests, and failed-run dataset detail.
- Saved sanitized fixtures:
  - `fixtures/a3/p3/ashr_dataset_probe_after_frontend_empty.redacted.json`
  - `fixtures/a3/p3/ashr_run_probe_after_frontend_empty.redacted.json`
  - `fixtures/a3/p3/ashr_request_probe_after_frontend_empty.redacted.json`
  - `fixtures/a3/p3/ashr_failed_run_dataset_detail.redacted.json`
- API returned populated objects:
  - 3 datasets
  - 2 runs
  - 5 requests
- Authenticated frontend still showed:
  - 0 UI-visible datasets on Datasets
  - 0 graded runs on Analytics
  - run-tests-first empty state on Trust

### Output

- Added `docs/a3/p3_api_frontend_visibility_gap.md`.
- Linked it from `docs/a3/p3_frontend_page_map.md`.
- Added checklist evidence in `docs/a3/acceptance_checklist.md`.

### Conclusion

The current gap is frontend visibility, not API availability. A3 should keep using sanitized API fixtures for populated run/case evidence until a UI-visible hosted run is available.

## 2026-07-06 - Frontend session expired

### Goal

Check whether the connected Chrome Lab session can still be used for frontend product calibration.

### Evidence

- Observed the current Lab frontend through read-only Chrome/CDP.
- The page showed sign-in UI and `Your session has expired. Please sign in again.`
- Frontend POST requests to `api.ashr.io/testing-platform-api` returned `401`.
- Saved sanitized fixture: `fixtures/a3/p3/ashr_frontend_session_expired_network.redacted.json`.

### Safety

- No headers, cookies, tokens, response bodies, or screenshots were saved.
- No sign-in or form-submit action was performed.

### Conclusion

Further frontend observation now requires fresh manual login. Local read-only API calibration through `.env.local` remains separate and continues to be the source of populated run/case evidence.

## 2026-07-06 - Signed media URL coverage audit

### Goal

Clarify whether A3 can safely render real Ashr signed media links.

### Evidence

- Scanned 18 redacted P3 fixtures under `fixtures/a3/p3`.
- Saved coverage fixture: `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`.
- Added documentation: `docs/a3/p3_signed_media_url_coverage.md`.
- Found 2 `signed_url` keys, both nearest to file-like actions.
- Found no audio/image/video `signed_url` sample.
- Confirmed `output_path` evidence exists for audio and file actions.

### Conclusion

A3 should preserve signed URL metadata in redacted form, but should not render live signed media links. Current evidence confirms file-like signed URL fields only; audio/image/video signed URL behavior remains unconfirmed.

## 2026-07-06 - Chinese P3/A3 handoff summary

### Goal

Give the student team a plain-language explanation of current A3/P3 status and remaining evidence gaps.

### Added

- `docs/a3/p3_status_handoff_cn.md`

### Summary

The handoff explains what A3 has completed, what the real Ashr API proved, what the real frontend observation proved, why frontend detail pages still need a fresh login and UI-visible populated run, why failure class remains derived, and why live signed media rendering is still out of scope.

## 2026-07-06 - Frontend relogin observation checklist

### Goal

Prepare a safe next-step checklist for frontend calibration after the user manually logs into Ashr Lab again.

### Added

- `docs/a3/p3_frontend_relogin_observation_checklist.md`

### Summary

The checklist covers observation order, required evidence, safety rules, stop conditions, and the minimum successful frontend pass: login valid, one UI-visible populated run, one run detail, one case detail, and confirmation of expected-vs-actual / trace / tool call / failure label presence.

## 2026-07-06 - Frontend relogin checked

### Goal

Continue frontend calibration after the user manually logged into Ashr Lab again.

### Evidence

- Connected read-only to Chrome through the local CDP port.
- Confirmed Lab top-level pages loaded with authenticated frontend API calls returning `200`.
- Saved sanitized summary: `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`.
- No headers, cookies, tokens, response bodies, screenshots, email, or account-specific values were saved.

### Findings

- Login is valid again; the earlier `401`/session-expired blocker is no longer the current issue.
- Datasets still shows 0 UI-visible datasets and `No datasets match your filters.`
- Analytics still shows 0 agents, 0 datasets, and 0 graded runs.
- Trust still shows the run-tests-first empty state.

### Conclusion

The remaining blocker is data visibility, not login. A3 can cite the real frontend for navigation, filters, analytics modules, usage/quota modules, empty states, and trust/report inspiration, but still needs one UI-visible populated hosted run before confirming real frontend run detail, case detail, expected-vs-actual, trace/timeline, and native frontend failure labels.

## 2026-07-06 - Usage / Quota media calibration panel

### Goal

Run the next A3 Commercial Growth iteration with media coverage included, using real Ashr API and official frontend evidence without creating or mutating real objects.

### Chosen ROI item

Selected Usage / Quota + Media calibration panel/report enhancement.

This was the best single step because it combines:

- media direction from the group lead
- real API calibration
- official frontend workflow calibration
- small A3-owned implementation scope
- clear demo value for non-developers

### Evidence

Saved redacted evidence:

- `fixtures/a3/p3/ashr_media_api_calibration.redacted.json`
- `fixtures/a3/p3/ashr_media_run_case_sample.redacted.json`
- `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`
- `fixtures/a3/p3/ashr_frontend_usage_workflow.redacted.json`
- `docs/a3/p3_media_frontend_notes.md`

API findings:

- Read-only media/API calibration saw 3 datasets, 5 requests, and 2 runs.
- Signed URL paths remain confirmed only for file-like action shape.
- Direct API-key calls to `get_usage` and `billing_get_status` returned 403 OAuth-only messages.

Frontend findings:

- Usage page shows Images, Audio, and Files quota modules.
- Usage page calls `get_usage` and `billing_get_status`.
- Datasets page calls `list_datasets`, `list_requests`, and `list_folder_memberships`.
- Trust page calls `get_trust_certificate_status` and `preview_trust_certificate`.

### Implemented

- Added `summarizeUsageQuota()` to report builder.
- Added `usage_quota` to JSON export.
- Added Usage / Quota section to Markdown export.
- Added Usage / Quota evidence to dashboard console and print/PDF preview.
- Added tests for dashboard wiring and report builder summary.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 35
pass 35
fail 0
```

Browser smoke:

- `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`

## 2026-07-06 - Official demo source 884/11925

- Added a dashboard data source for the official A3 refund demo: `P3 Official Demo 884/11925`.
- The source maps hosted Ashr run `11925` from dataset `884` into the existing A3 Run List, Case Detail, Expected vs Actual, Tool Call Diff, Failure Clusters, Media Readiness, and Report export flow.
- Updated P3 mapper support for official dataset wrappers under `response.dataset`.
- Preserved generated dataset media action types in `media_evidence`, so the official demo now exposes audio, file, and image channels in A3.
- Added tests for the official demo source and generated-dataset request provenance.
- Verification passed:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
tests 41
pass 41
fail 0
```

- Browser smoke passed at `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-demo-884-11925.png`.

## 2026-07-06 - Official frontend dataset 884 observation

- Connected to the user's authenticated normal Chrome session through local CDP.
- Opened official Ashr dataset `884`.
- Confirmed official frontend shows `A3 Refund Demo Dataset`, Overview, `Test cases (5)`, and `Results (0)`.
- Confirmed official Test cases page shows the five generated refund cases with title, key, description, action count, and tag count.
- Opened `happy_path_text_valid_booking` in the official frontend.
- Confirmed official case detail shows TEST DETAILS, tags, ACTIONS, User/Agent actors, TEXT/AUDIO labels, and Tool Calls.
- Clicked `Open Most Recent Run`; official frontend still showed `Runs History / No runs found`.
- Tried direct `run=11925`; official frontend returned to dataset overview and did not show run `11925`.
- Added redacted evidence: `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`.
- Updated docs to clarify the current gap: A3 can display API run `11925` locally, but official Results does not list that API-created run.
- Confirmed Usage / Quota renders Images/Audio/Files evidence and OAuth-gated API status.
- Saved screenshot: `docs/screenshots/a3-dashboard-usage-quota-media.png`.

## 2026-07-06 - Official Ashr dashboard gap panel

### Goal

Compare the current A3 dashboard with the official Ashr Lab product structure and improve the safest, highest-value gap without copying account/security/cloud administration features.

### Evidence used

- Existing authenticated frontend page map: `docs/a3/p3_frontend_page_map.md`
- Existing frontend-to-MVP gap doc: `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- Existing MVP recommendations: `docs/a3/p3_a3_mvp_recommendations.md`
- Existing redacted P3 API/frontend fixtures

No new real Ashr API calls were required for this round.

### Finding

A3 already covers the core evaluation workflow: run list, case detail, expected vs actual, trace timeline, tool-call diff, failure clusters, media evidence, and report export.

The largest remaining product difference is the official cloud-console shell: Datasets, Agents, Folders, Analytics, Usage, Trust, API Keys, and Team. For the student MVP, only the evaluation-review and reporting ideas should be copied. Account, key, team, billing, OAuth, public trust publishing, and hosted mutation flows remain out of scope.

### Implemented

- Added `docs/a3/p3_official_dashboard_gap_analysis.md`.
- Added `summarizeOfficialAshrGap()` in `services/report/report_builder.mjs`.
- Added `official_ashr_gap` to JSON reports.
- Added `Official Ashr Gap` to Markdown reports.
- Added an `Official Ashr Gap` dashboard panel.
- Added the same gap map to the print/PDF report preview.
- Added dashboard and report-builder test coverage.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 37
pass 37
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed `Official Ashr Gap` dashboard panel renders.
- Confirmed print/PDF report preview includes `Official Ashr Gap`.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-gap.png`.

### Safety

- No real key, token, cookie, email, or signed URL was printed or saved.
- No `.env.local` change.
- No real Ashr create/delete/publish/invite/key-management action.
- Changes stayed inside A3-owned dashboard/report/test/doc paths.

## 2026-07-06 - Media readiness and cloud console polish

### Goal

Improve the A3 dashboard in the areas requested by the team: more media direction, a more polished product console, and a safe imitation of official login/cloud/admin product logic.

### Scope decision

Implemented:

- media readiness display
- signed URL safety posture
- official-style read-only cloud console shell
- UI polish for product-console feel
- JSON/Markdown/print report support

Not implemented:

- real login/OAuth
- real API-key create/revoke/show-secret UI
- real team invites
- billing or upgrade mutations
- real cloud create/delete/publish operations
- live signed media URL rendering

### Implemented

- Added `summarizeMediaReadiness()` in `services/report/report_builder.mjs`.
- Added `summarizeCloudConsoleShell()` in `services/report/report_builder.mjs`.
- Added JSON export fields:
  - `media_readiness`
  - `cloud_console_shell`
- Added Markdown/print sections:
  - `Media Readiness`
  - `Cloud Console Shell`
- Added dashboard panels:
  - `Media Readiness`
  - `Cloud Console Shell`
- Added dashboard polish:
  - sidebar brand mark
  - topbar safety/status chips
  - Media and Cloud Shell nav entries
  - clearer badges and product-console panel styling
- Added documentation: `docs/a3/p3_media_cloud_console_polish.md`.
- Added dashboard/report-builder test coverage.

### Evidence

Used existing redacted fixtures only:

- `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`
- `fixtures/a3/p3/ashr_auth_check.redacted.json`
- `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 39
pass 39
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed `Media Readiness` renders with 6 rows.
- Confirmed `Cloud Console Shell` renders with 8 rows.
- Confirmed print/PDF report preview includes `Media Readiness`.
- Confirmed print/PDF report preview includes `Cloud Console Shell`.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-cloud-polish.png`
  - `docs/screenshots/a3-dashboard-cloud-shell.png`

### Safety

- No real Ashr API calls were required for this round.
- No key, token, cookie, email, browser header, account value, or raw signed URL was saved.
- `.env.local` was not modified.
- All cloud/admin behavior remains local read-only status display.

## 2026-07-06 - Media matrix and cloud action guardrails

### Goal

Continue polishing the media/cloud dashboard so it explains exact readiness and action boundaries, not just high-level status.

### Implemented

- Added a Media Channel Matrix inside `summarizeMediaReadiness()`.
- The matrix covers:
  - audio
  - files
  - images
  - video
  - VM stream
- Each media channel now reports:
  - usage/frontend observation
  - case evidence count
  - output path confirmation
  - signed URL confirmation
  - live preview policy
  - A3 decision
- Added Cloud Action Guardrails inside `summarizeCloudConsoleShell()`.
- The guardrails separate safe local actions from disabled official cloud/admin actions:
  - local fixture switching
  - local export
  - local print/PDF
  - auth/workspace/request/usage read-only viewing
  - disabled OAuth login
  - disabled hosted dataset creation
  - disabled API-key mutation
  - disabled team invite
  - disabled billing upgrade
  - disabled Trust publishing
  - disabled cloud deletion
- Dashboard now renders:
  - `media-channel-matrix`
  - `cloud-action-list`
- Print/PDF report now includes both tables.
- JSON/Markdown report already include both through `media_readiness` and `cloud_console_shell`.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 39
pass 39
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Media Channel Matrix renders 5 rows.
- Confirmed Cloud Action Guardrails renders 15 rows.
- Confirmed print/PDF report includes cloud guardrail actions.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-matrix.png`
  - `docs/screenshots/a3-dashboard-cloud-guardrails.png`

### Safety

- Still no real Ashr API calls.
- Still no `.env.local` changes.
- Still no live signed URL rendering.
- Still no real login, key, team, billing, trust, create, delete, or publish action.

## 2026-07-07 - Official UI-compatible run 11926

### Why this was needed

The earlier hosted run `11925` existed through the API, but it used the local clone's `result.cases[]` structure. Official Ashr frontend evidence points to the Results UI reading `result.tests[].action_results[]`, so A3 needed a closer official-shape run before saying the result path was properly tested.

### Work completed

- Built `fixtures/a3/p3/ashr_dataset_884_demo_run_result.official_ui_tests.synthetic.json`.
- Created exactly one real Ashr run for dataset `884` using the official-style `tests[]` result shape.
- New run id: `11926`.
- Confirmed `get_run(11926)` returns 5 tests.
- Confirmed `list_runs(dataset_id=884)` returns `11926`.
- Confirmed frontend-style `list_runs(dataset_id=884, summary_only=true)` returns `11926`.
- Updated dashboard source `p3-official-demo` from run `11925` to run `11926`.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-demo-884-11926.png`.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 41
pass 41
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed run `11926`, 5 cases, 40% pass rate, 56.4 average score, 5 media-evidence cases.

### Remaining gap

The in-app browser was not logged in to Ashr Lab, so this round did not visually confirm the official Results tab. The next manual/browser step is to refresh `https://lab.ashr.io/?tab=analysis&dataset=884` in a logged-in Ashr browser and check whether Results lists run `11926`.

## 2026-07-07 - Commercial Release Gate

### Goal

Move A3 closer to a paid release-intelligence workflow by adding a release gate that can tell a team whether an agent release should be approved, reviewed, or blocked.

### Work completed

- Added `summarizeReleaseGate()` in `services/report/report_builder.mjs`.
- Added `release_gate` to JSON report export.
- Added `## Release Gate` to Markdown report export.
- Added Release Gate section to print/PDF report preview.
- Added Release Gate dashboard panel.
- Added dashboard wiring tests for the panel and render loop.
- Added report-builder tests for blocked risky evidence and approved clean evidence.
- Added Growth-Auditor handoff:
  - `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-release-gate-11926.png`

### Current official demo gate result

For dataset `884` / run `11926`:

- Decision: `Block release`
- Risk score: `70`
- Failed checks: `2`
- Blocks merge: `yes`
- Required approvers: `4`

Why blocked:

- 40% pass rate is below the 95% commercial release threshold.
- One case has `missing_required_tool`.

### Verification

Command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 43
pass 43
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed Release Gate renders `Block release`, risk score, failed checks, blockers, and approver count.

### Commercial value

This is the first A3 feature that directly maps to a paid enterprise workflow: block risky agent releases, generate reviewer evidence, and give managers a sign-off artifact.

## 2026-07-07 - PR Gate workflow and audit bundle

### Goal

Turn the local Release Gate into a PR-facing and audit-facing workflow that looks closer to a commercial release-intelligence product.

### Work completed

- Added `summarizeReleaseWorkflow()` in `services/report/report_builder.mjs`.
- Added a GitHub Check payload shape:
  - check name: `Ashr++ Release Gate`
  - conclusion: `success`, `neutral`, or `failure`
  - blocks-merge signal
  - output title, summary, and evidence text
- Added a PR comment Markdown template.
- Added waiver policy:
  - required fields
  - exceptional-only waiver for blocked releases
  - 1-day maximum expiry for blocked releases
- Added reviewer workflow:
  - review state
  - release/safety/runner/judge/evidence/A3 review lanes
  - next actions
- Added audit bundle manifest:
  - JSON report
  - Markdown report
  - print/PDF report
  - case evidence
  - redacted fixtures
  - screenshot evidence
- Added incident replay pack from top-risk failed cases.
- Added `release_workflow` to JSON report export.
- Added `## PR Gate / Review Workflow` to Markdown report export.
- Added `PR Gate & Audit` dashboard panel.
- Added `PR Gate & Audit Workflow` to print-ready report preview.

### Evidence

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-pr-gate-audit-11926.png`

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 44
pass 44
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed `PR Gate & Audit` renders check conclusion `failure`, blocks merge `yes`, waiver required `yes`, waiver max `1d`, and audit bundle artifacts.

### Commercial value

A3 now emits the artifacts a buyer expects around release control: a PR check payload, a PR comment body, waiver guidance, reviewer lanes, audit manifest, and incident replay case list. It is still not a live GitHub required check, but the contract shape is now present and tested.

## 2026-07-07 - Gate CLI contract and hashed audit manifest

### Goal

Turn the release gate workflow into a command-shaped artifact that future CI and GitHub PR checks can consume.

### Work completed

- Added `services/report/a3_gate_cli.mjs`.
- Added `buildGateCliPayload()` for programmatic gate packaging.
- Added `renderGateCliMarkdown()` for human-readable gate output.
- Added command arguments:
  - `--runs`
  - `--grades`
  - `--coverage`
  - `--thresholds`
  - `--release-version`
  - `--environment`
  - `--owner`
  - `--source`
  - `--json`
  - `--markdown`
  - `--strict-exit`
  - `--no-fail`
- Added `fixtures/a3/release_gate_thresholds.json`.
- Added configurable release thresholds to `summarizeReleaseGate()`.
- Added threshold values to `release_gate`.
- Added hashed audit manifest for CLI input files.
- Added workspace-relative artifact paths to avoid writing local user directories into CLI output.
- Added separate exit behavior:
  - `--strict-exit` for CI merge blocking
  - `--no-fail` for local report generation
- Added redacted CLI evidence fixture:
  - `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- Added tests:
  - `tests/a3/a3_gate_cli.test.mjs`

### Verification

Focused command:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

### Commercial value

This gives A3 the first real CI-shaped contract: `ashr gate --json`. A future GitHub Action can run this command, read `release_workflow.github_check`, attach the PR comment, and block merge when `release_gate.pr_gate.blocks_merge` is true.

### Follow-up hardening

- Added output file options:
  - `--output-json`
  - `--output-md`
  - `--output-check`
  - `--output-pr-comment`
- Added GitHub Check Run payload output with annotations for top-risk cases.
- Added PR comment Markdown file output.
- Added lightweight output redaction scrubber.
- Added committed redacted PR artifacts:
  - `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
  - `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`
  - `fixtures/a3/p3/a3_gate_cli_report.redacted.md`
- Expanded CLI tests to cover output files, annotations, redaction, and committed artifacts.

Updated verification:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 7
pass 7
fail 0
```

## 2026-07-07 - GitHub dry-run request adapter

### Goal

Turn the existing A3 gate CLI payload into GitHub-shaped dry-run requests before any live GitHub token or required check is introduced.

### Work completed

- Added `services/report/a3_github_integration.mjs`.
- Added `buildGitHubCheckRunRequest()` for create/update Check Run request shapes.
- Added `buildPrCommentUpsertPlan()` for marker-based PR comment create/update plans.
- Added `buildGitHubActionWorkflowExample()` for a future GitHub Actions workflow.
- Required callers to pass a current `headSha` so stale fixture SHAs are not reused.
- Let caller-provided `detailsUrl` override fixture/demo URLs.
- Generated redacted dry-run fixtures:
  - `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
  - `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`
- Generated workflow example:
  - `docs/a3/p3_github_action_workflow_example.yml`
- Added focused test coverage:
  - `tests/a3/a3_github_integration.test.mjs`
- Documented the round:
  - `docs/a3/p3_github_dry_run_integration_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
tests 6
pass 6
fail 0
```

### Current interpretation

A3 can now produce safe GitHub-shaped release gate artifacts without calling GitHub. This is still dry-run only: no GitHub API call, no token, no real PR comment, and no required check has been created.

## 2026-07-07 - Generated artifact manifest for enterprise audit

### Goal

Hash the files generated by the A3 Gate CLI so an enterprise reviewer can verify that exported release evidence was not changed after generation.

### Work completed

- Added `buildGeneratedArtifactManifest()` in `services/report/a3_gate_cli.mjs`.
- Added CLI option:
  - `--output-manifest`
- The manifest now records hashes for:
  - JSON gate report
  - Markdown gate report
  - GitHub Check Run payload
  - PR comment Markdown
- The manifest records:
  - schema version `a3.generated_artifact_manifest.v1`
  - run id
  - release decision
  - risk score
  - merge-blocking status
  - GitHub check conclusion
  - content type
  - byte size
  - SHA-256
  - workspace-relative path
- Added committed redacted manifest fixture:
  - `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- Added tests for generated artifact hash correctness and redacted paths.
- Added documentation:
  - `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 9
pass 9
fail 0
```

### Current interpretation

A3 now hashes both sides of the gate evidence chain: input fixtures in `audit_manifest.artifacts` and generated output files in `a3.generated_artifact_manifest.v1`. This is still not a signed immutable audit bundle, but it is a stronger foundation for enterprise sign-off.

## 2026-07-07 - File-backed waiver validation

### Goal

Move waiver handling from policy text into a local validation contract that can support enterprise review.

### Work completed

- Added `validateWaiverRequest()` in `services/report/a3_gate_cli.mjs`.
- Added CLI arguments:
  - `--waiver`
  - `--generated-at`
- Added `waiver_review` to Gate CLI JSON output.
- Added waiver file hashing to `audit_manifest.artifacts`.
- Added Waiver Review section to the Markdown report.
- Added redacted waiver fixtures:
  - `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`
- Added tests for:
  - valid exceptional waiver
  - expired/incomplete waiver rejection
  - committed waiver review fixture
  - Markdown Waiver Review output
- Added documentation:
  - `docs/a3/p3_waiver_validation_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_waiver_workflow_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 12
pass 12
fail 0
```

### Current interpretation

A3 can now validate waiver evidence locally. A valid waiver is evidence for reviewer sign-off, not an automatic unblock: blocked releases still remain blocked until a future live policy explicitly changes CI behavior.

## 2026-07-07 - File-backed signed approval validation

### Goal

Move exception approval from informal sign-off into a structured local approval validation contract.

### Work completed

- Added `validateApprovalRecord()` in `services/report/a3_gate_cli.mjs`.
- Added CLI argument:
  - `--approval`
- Added `approval_review` to Gate CLI JSON output.
- Added approval file hashing to `audit_manifest.artifacts`.
- Added Approval Review section to the Markdown report.
- Added redacted approval fixtures:
  - `fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json`
- Added tests for:
  - valid exception approval
  - invalid too-permissive approval
  - missing required signer roles
  - self-approval separation-of-duties failure
  - committed approval review fixture
  - Markdown Approval Review output
- Added documentation:
  - `docs/a3/p3_signed_approval_validation_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_signed_approval_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 15
pass 15
fail 0
```

### Current interpretation

A3 can now validate file-backed approval evidence for a blocked-release exception. This is not cryptographic signing and not durable backend persistence yet; it is the local contract needed before approval records can be bound to GitHub/OIDC/SSO identities and immutable audit bundles.

## 2026-07-07 - Audit bundle index and root hash

### Goal

Turn the scattered A3 gate artifacts into one audit bundle index with a stable root hash and a local chain-of-custody trail.

### Work completed

- Added `buildAuditBundleIndex()` in `services/report/a3_gate_cli.mjs`.
- Added CLI option:
  - `--output-bundle`
- Added schema:
  - `a3.audit_bundle_index.v1`
- Added bundle root hash generation over canonical JSON.
- Added self-hash exclusion so the bundle index does not hash its own file bytes.
- Added artifact grouping:
  - source inputs
  - generated outputs
  - governance records
  - custody records
- Added chain-of-custody events:
  - `gate_built`
  - `input_artifacts_hashed`
  - `generated_artifacts_hashed`
  - `waiver_reviewed`
  - `approval_reviewed`
  - `bundle_index_written`
- Added byte size and content type metadata for input audit artifacts.
- Added redacted bundle fixture:
  - `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- Added Growth-Auditor report:
  - `docs/a3/p3_growth_auditor_audit_bundle_index_2026_07_07.md`
- Added implementation doc:
  - `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`
- Added tests in:
  - `tests/a3/a3_gate_cli.test.mjs`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Focused result after this pass: all A3 Gate CLI tests pass.

### Current interpretation

A3 now has the local evidence package layer that sits above gate JSON, Markdown report, GitHub check payload, waiver, and approval. This is not immutable enterprise storage yet, but it is the root-hash contract future storage, verifier, and GitHub artifact upload can rely on.

## 2026-07-07 - Audit bundle verifier

### Goal

Add the verification command that proves an A3 audit bundle index still matches its artifact hashes and custody event hashes.

### Work completed

- Added `verifyAuditBundleIndex()` in `services/report/a3_gate_cli.mjs`.
- Added `renderBundleVerificationMarkdown()` in `services/report/a3_gate_cli.mjs`.
- Added CLI option:
  - `--verify-index`
- Added verification schema:
  - `a3.audit_bundle_verification.v1`
- Verification now checks:
  - bundle root hash
  - artifact SHA-256 hashes
  - artifact byte sizes
  - missing artifact files
  - unsafe local paths
  - custody event hashes
  - `previous_event_hash` chain links
- Added redacted verification fixture:
  - `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- Added implementation doc:
  - `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`
- Added tests in:
  - `tests/a3/a3_gate_cli.test.mjs`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Focused result after this pass:

```text
tests 20
pass 20
fail 0
```

### Current interpretation

A3 can now generate a local audit bundle index and verify it later. This closes the first verifier gap and makes the bundle/root-hash work actually usable by reviewers and auditors.

## 2026-07-07 - Official frontend mirror clean-room integration

### Goal

Use the offline Ashr frontend mirror as product-reference evidence without copying official source code or sensitive browser/session data.

### Work completed

- Added report-builder summary support for the clean-room frontend mirror fixture.
- Added JSON export field:
  - `official_frontend_mirror`
- Added Markdown report section:
  - `Official Frontend Mirror`
- Added dashboard panel:
  - `Official Frontend Mirror`
- Added print/PDF report section for the frontend mirror summary.
- Wired the dashboard to load:
  - `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json`
- Added tests in:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Added implementation note:
  - `docs/a3/p3_frontend_mirror_analysis_2026_07_07.md`
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-official-frontend-mirror.png`

### Current interpretation

The mirror is now represented as a clean-room product map: official navigation, API method groups, visible labels, copy/partial/future/out-of-scope decisions, and safety boundaries. A3 still does not copy official code, assets, OAuth, key management, billing, team administration, cookies, tokens, or raw signed URLs.

## 2026-07-07 - Release War Room

### Goal

Turn the existing Release Gate, PR Gate, incident replay, audit evidence, and official frontend parity signals into one reviewer-facing release decision packet.

### Work completed

- Added `summarizeReleaseWarRoom()` in `services/report/report_builder.mjs`.
- Added schema:
  - `a3.release_war_room.v1`
- Added JSON export field:
  - `release_war_room`
- Added Markdown report section:
  - `Release War Room`
- Added dashboard panel:
  - `Release War Room`
- Added print/PDF report section:
  - `Release War Room`
- Added redacted fixture:
  - `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- Added implementation doc:
  - `docs/a3/p3_release_war_room_growth_2026_07_07.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_release_war_room_2026_07_07.md`
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-release-war-room.png`
- Added tests in:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`

### Current interpretation

The Release War Room is the first A3 operational cockpit over release evidence. It gives a no-go/review/ship-ready decision, revenue risk score, merge-block status, waiver requirement, incident replay count, required audit artifact count, reviewer lanes, and official-product parity context. It does not call live APIs and does not store secrets, cookies, tokens, or live signed URLs.

## 2026-07-07 - Official Parity Roadmap and Media Evidence Queue

### Goal

Move the official frontend mirror summary from background evidence into an actionable dashboard/report roadmap, and make media evidence review more concrete.

### Work completed

- Re-checked A1/A2 handoff assumptions through A3 tests:
  - A1-style run/trace/tool-call fixtures still feed A3 normalization and tool-call diff logic.
  - A2 G3 grade/coverage fixtures still join into A3 reports and filters.
- Added dashboard panel:
  - `Official Parity Roadmap`
- Added Media Readiness sub-panel:
  - `Media Evidence Queue`
- Added print/PDF report section:
  - `Official Parity Roadmap`
- Updated Report Center copy to include official parity roadmap evidence.
- Added report-builder tests for:
  - `summarizeOfficialParityRoadmap()`
  - `media_readiness.evidence_queue`
  - JSON export `official_parity_roadmap`
  - Markdown `Official Parity Roadmap`
- Added dashboard wiring tests for:
  - roadmap panel IDs/functions
  - media evidence queue IDs/functions
- Added implementation note:
  - `docs/a3/p3_official_parity_media_queue_2026_07_07.md`
- Saved browser verification screenshots:
  - `docs/screenshots/a3-dashboard-official-parity-media-queue.png`
  - `docs/screenshots/a3-dashboard-media-evidence-queue.png`
  - `docs/screenshots/a3-dashboard-media-evidence-queue-detail.png`

### Verification

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
76 tests
76 pass
0 fail
```

### Current interpretation

A3 now explains not only what it already copied from official Ashr, but also the next build order and the cloud/admin boundaries that should remain disabled. Media evidence is still metadata-only, but reviewers can now see which cases are queued for media review and what evidence is missing.

## 2026-07-07 - Incident Replay Queue

### Goal

Upgrade A3 from a release dashboard into a replay-first incident review workflow.

### Work completed

- Added `summarizeIncidentReplayQueue()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `incident_replay_queue`
- Added Markdown report section:
  - `Incident Replay Queue`
- Added dashboard panel:
  - `Incident Replay`
- Added print/PDF report section:
  - `Incident Replay Queue`
- Updated Report Center copy to include incident replay evidence.
- Added report-builder tests that prove the replay queue packages:
  - A1 trace / observation readiness
  - A1 tool-call diff evidence
  - A2 judge evidence
  - media metadata evidence
  - reviewer packet artifacts
- Added dashboard wiring tests for the Incident Replay panel.
- Added implementation note:
  - `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-incident-replay-queue.png`

### Verification

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
78 tests
78 pass
0 fail
```

### Current interpretation

Incident Replay Queue is a commercial workflow, not a cosmetic list. It turns failed cases into ranked replay packets with owner lanes, trace readiness, tool-call divergence, A2 judge evidence, media metadata, and release-blocker state. This moves A3 closer to a platform that can stop risky releases and help reviewers reproduce failures before sign-off.

## 2026-07-07 - Reviewer Workflow Board

### Goal

Convert incident replay evidence into an owned reviewer workflow board.

### Work completed

- Added `summarizeReviewerWorkflowBoard()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `reviewer_workflow_board`
- Added Markdown report section:
  - `Reviewer Workflow Board`
- Added dashboard panel:
  - `Reviewer Workflow`
- Added print/PDF report section:
  - `Reviewer Workflow Board`
- Added reviewer lanes, review states, missing-artifact checks, waiver state, approval readiness, and next actions.
- Kept the board calibrated to:
  - A1 trace and observation readiness
  - A1 tool-call diffs
  - A2 judge evidence
  - A2 coverage availability
  - metadata-only media evidence
- Added report-builder tests for the reviewer workflow board.
- Added dashboard wiring tests for the Reviewer Workflow panel and print report.
- Added implementation note:
  - `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`
- Included Growth-Auditor note:
  - `docs/a3/p3_growth_auditor_reviewer_workflow_2026_07_07.md`
- Browser-smoke verified Reviewer Workflow with `Blocked`, 3 open official-demo items, 6 reviewer lanes, and A1/A2 calibration counts.
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-reviewer-workflow-board.png`

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
44 tests
44 pass
0 fail
```

Full command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
80 tests
80 pass
0 fail
```

### Current interpretation

Reviewer Workflow Board is the next layer after Incident Replay Queue. Incident Replay says which failed cases must be replayed; Reviewer Workflow says who owns them, what evidence is missing, and whether waiver or approval can proceed. This makes A3 closer to a release-governance product while still staying local-only and safe.

## 2026-07-07 - Official Code Crawl Parity

### Goal

Use the official Ashr frontend mirror as clean-room product evidence and convert code-level page/module signals into A3 parity reporting.

### Work completed

- Added redacted code-crawl fixture:
  - `fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json`
- Added `summarizeOfficialCodeCrawlParity()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `official_code_crawl_parity`
- Added Markdown report section:
  - `Official Code Crawl Parity`
- Added dashboard panel:
  - `Official Code Crawl`
- Added print/PDF report section:
  - `Official Code Crawl Parity`
- Added report-builder tests proving the crawl summary does not commit official source and maps A3 copy/out-of-scope decisions.
- Added dashboard-wiring tests for fixture loading, panel IDs, renderers, exports, and print report.
- Added implementation note:
  - `docs/a3/p3_official_code_crawl_parity_growth_2026_07_07.md`
- Added clean-room explorer note:
  - `docs/a3/p3_official_frontend_code_crawl_cleanroom_2026_07_07.md`
- Added Growth-Auditor note:
  - `docs/a3/p3_growth_auditor_code_crawl_parity_2026_07_07.md`
- Browser-smoke verified Official Code Crawl with 9 chunk rows, 6 parity target rows, and `source committed no`.
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-official-code-crawl-parity.png`

### A1/A2 calibration

- Results review maps back to A1 run/case/trace plus A2 score/pass/fail/failure class.
- Trace observability maps back to A1 trace/tool-call evidence plus A2 judge remediation.
- Media evidence maps back to A1 media metadata and A2 media failure taxonomy.
- Trust/audit maps back to A1/A2 evidence packaged by A3 report, audit bundle, and verifier.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
46 tests
46 pass
0 fail
```

Full command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
82 tests
82 pass
0 fail
```

### Current interpretation

Official Code Crawl Parity gives A3 a stronger product reference without copying official source. It shows which official frontend chunks imply results review, trace observability, media evidence, trust/audit, usage, API keys, and team admin. A3 should copy the release-intelligence workflow and keep admin, billing, and secret flows out of scope.

## 2026-07-07 - Observability Replay Matrix

### Goal

Turn failed-case replay into production-style observability replay evidence.

### Work completed

- Added `summarizeObservabilityReplayMatrix()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `observability_replay_matrix`
- Added Markdown report section:
  - `Observability Replay Matrix`
- Added dashboard panel:
  - `Observability Replay`
- Added print/PDF report section:
  - `Observability Replay Matrix`
- Added replay lanes for:
  - trace timeline
  - tool errors
  - latency / duration
  - A2 judge link
  - media metadata
  - official Observability parity
- Added per-case production replay items with production risk, observability state, trace counts, tool/error counts, judge counts, media counts, and next action.
- Added implementation note:
  - `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`
- Added clean-room explorer note:
  - `docs/a3/p3_observability_replay_cleanroom_2026_07_07.md`
- Added Growth-Auditor note:
  - `docs/a3/p3_growth_auditor_observability_replay_2026_07_07.md`

### A1/A2/Official calibration

- A1 supplies trace events, observations, tool-call diffs, latency/duration fields, and tool-error text.
- A2 supplies score, pass/fail, primary failure class, judge evidence, and remediation.
- Official code crawl supplies ObservabilityPage / trace / latency / error product signals without copying official source.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
48 tests
48 pass
0 fail
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
84 tests
84 pass
0 fail
```

Browser smoke:

- Opened the local dashboard with the official demo source.
- Confirmed `Observability Replay`, `Trace Timeline`, and `Official Observability Parity` render.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-observability-replay-matrix.png`

### Current interpretation

Observability Replay Matrix is the production replay layer A3 was missing. It connects incident replay to trace evidence, tool/error evidence, A2 judge findings, media metadata, and official Observability parity. This moves A3 closer to a sellable release-intelligence platform that can block risky agent releases and support incident review.

## 2026-07-07 - Regression Factory

### Goal

Turn failed incident replay cases into regression-test candidates for the next release gate.

### Work completed

- Added `summarizeRegressionFactory()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `regression_factory`
- Added Markdown report section:
  - `Regression Factory`
- Added dashboard panel:
  - `Regression Factory`
- Added print/PDF report section:
  - `Regression Factory`
- Added per-candidate fields:
  - regression id
  - generator state
  - owner lane
  - coverage status
  - required contracts
  - proposed assertions
  - generated artifact plan
  - next action
- Added implementation note:
  - `docs/a3/p3_regression_factory_growth_2026_07_07.md`
- Added contract delta note from integration explorer:
  - `docs/a3/p3_a1_a2_a3_contract_delta_2026_07_07.md`
- Added official frontend parity backlog:
  - `docs/a3/p3_official_frontend_parity_backlog_2026_07_07.md`
- Added Growth-Auditor round note:
  - `docs/a3/p3_growth_auditor_round_2026_07_07_enterprise_push.md`

### A1/A2/Official calibration

- A1 supplies trace, observation, expected vs actual, tool-call, media metadata, and replay evidence.
- A2 supplies pass/fail, score, primary failure class, judge evidence, severity, remediation, and coverage.
- Official code crawl supplies Results review parity signals without copying official source.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
50 tests
50 pass
0 fail
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
86 tests
86 pass
0 fail
```

Browser smoke:

- Opened the local dashboard with the official demo source.
- Confirmed `Regression Factory`, candidate count, coverage information, A1 Trace Capture, and A2 Judge Contract render.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-regression-factory.png`

### Current interpretation

Regression Factory is the next commercial layer after Incident Replay and Observability Replay. Incident Replay says what failed, Observability Replay says whether the evidence is replayable, and Regression Factory says whether the failure can become a repeatable regression candidate before the next release. This moves A3 closer to a paid release-intelligence workflow instead of a one-time demo dashboard.

## 2026-07-07 - Export Redaction Firewall And Dashboard Webapp Split

### Goal

Improve A3 enterprise export safety, strengthen A1/A2 data compatibility, and migrate the dashboard away from a single oversized HTML file.

### Work completed

- Added shared export firewall module:
  - `services/report/export_redaction_firewall.mjs`
- Added `summarizeExportRedactionFirewall()` to `services/report/report_builder.mjs`.
- Added `export_redaction_firewall` to JSON report exports.
- Added `Export Redaction Firewall` to Markdown and print/PDF report output.
- Added CSV cell scrubbing and formula-injection hardening.
- Reused the shared firewall from the A3 Gate CLI.
- Added dashboard `Export Safety` panel.
- Split dashboard webapp files:
  - `apps/dashboard/index.html`
  - `apps/dashboard/src/app.mjs`
  - `apps/dashboard/src/styles.css`
- Reduced `index.html` from more than 3,000 lines to about 400 lines.
- Strengthened A1/A2 input normalization in `report_builder.mjs`.
- Added direct compatibility for:
  - A1 RunResult root fixtures
  - A1 loose case lists
  - A1 `ashr.clone.run.v1` run fixture shape
  - A2 single run fixtures
  - A2 single local judge result fixtures
  - Existing A3 aggregate run fixtures
  - Existing A2 aggregate grade reports
- Added implementation note:
  - `docs/a3/p3_dashboard_webapp_migration_2026_07_07.md`
- Added Export Redaction Firewall docs:
  - `docs/a3/p3_growth_auditor_redaction_firewall_2026_07_07.md`
  - `docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md`

### A1/A2 calibration

- A1 compatibility now maps agent output, expected output, tool calls, observations, trace events, and optional media evidence into A3 case fields.
- A2 compatibility now maps single judge results and aggregate grade reports into pass/fail, score, failure class, severity, judge modes, and remediation evidence.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
55 tests
55 pass
0 fail
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
91 tests
91 pass
0 fail
```

Browser smoke:

- Served local dashboard at `http://127.0.0.1:4173/apps/dashboard/index.html`.
- Confirmed split webapp loads `src/app.mjs` and `src/styles.css`.
- Confirmed dashboard renders 32 cases, 6.3% pass rate, and Export Safety status `passed`.
- Browser console error log was empty.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-webapp-export-safety.png`

### Current interpretation

A3 is now less brittle. It no longer depends only on hand-shaped mock fixtures, and the dashboard is easier for the team to maintain because HTML, JS, and CSS have separate ownership boundaries.
