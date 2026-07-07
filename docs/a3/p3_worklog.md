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

## 2026-07-04 - Tool-call diff follow-up

### Goal

Continue the next A3 backlog item after media evidence: make expected vs actual tool-call failures readable without manual JSON comparison.

### Implemented

- Added `buildToolCallDiffs(caseResult)` in `services/report/report_builder.mjs`.
- Added normalized tool-call comparison statuses:
  - `match`
  - `missing_required_tool`
  - `unexpected_tool_call`
  - `wrong_tool`
  - `wrong_arguments`
- Added `tool_call_diffs` to JSON export output.
- Added dashboard `Tool Call Diff` panel in Case Detail.
- Added `docs/a3/p3_tool_call_diff.md`.
- Added screenshot `docs/screenshots/a3-p3-tool-call-diff.png`.

### Verification

- `node --test tests/a3/report_builder.test.mjs`: 5 tests passed.
- `node --test tests/a3/p3_ashr_mapper.test.mjs`: 5 tests passed.
- Browser smoke at `http://127.0.0.1:5173/apps/dashboard/index.html`.
- Confirmed missing tool case renders `missing_required_tool`.
- Confirmed wrong argument case renders `wrong_arguments`.
- Confirmed no horizontal overflow in the desktop browser check.

### Next top 3

1. Add field-level argument highlighting inside the tool-call diff.
2. Add report-center page with saved report history and PDF-ready layout.
3. Observe authenticated Ashr Lab after manual login and update official frontend notes.

## 2026-07-06 - Authenticated Lab frontend observation

### Goal

Continue P3 frontend/product-logic calibration after the user successfully logged into a browser session. Confirm real Lab navigation and UI workflow without saving secrets, cookies, screenshots, or account-specific values.

### Browser/login path

- Normal Edge and normal Chrome were visible but could not be inspected because the automation safety layer could not verify the current browser URL.
- Codex in-app browser could open Ashr, but Google login returned `400 Bad Request`.
- Launched an isolated Chrome profile with local CDP debugging on port `9222`.
- The user manually logged into Ashr in that isolated Chrome profile.
- Codex connected read-only through local CDP after login.

### Confirmed authenticated Lab pages

- `?tab=analysis`: Datasets page with search, Type/Agent/Creator/Status/Runs/time filters, pinned-only, sort, group, and `New dataset`.
- `?tab=agents`: Agents page; current account showed `No agents yet`.
- `?tab=folders`: Folders page with search and `New folder`; current account showed no folders.
- `?tab=analytics`: Analytics page with agents, datasets, graded runs, overall pass rate, run volume, pass-rate trend, runs by agent, and pass rate by agent.
- `?tab=usage`: Usage page with Images, Audio, and Files quota counters.
- `?tab=trust`: Trust page with public trust/certificate preview and frozen-metrics language.
- `?tab=api-keys`: API Keys page with create/setup instructions; no secret values were saved.
- `?tab=team`: Team management page; account-specific values were not saved.
- Settings menu: Theme and Low Power.
- New Dataset modal: 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.

### Documentation updated

- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_workflow_notes.md`
- `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- `docs/a3/p3_frontend_field_mapping.md`
- `docs/a3/p3_a3_mvp_recommendations.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/a3/acceptance_checklist.md`

### Safety

- Did not print, document, or commit the Ashr key.
- Did not read browser cookies or tokens.
- Did not save authenticated screenshots.
- Did not submit forms, create datasets, create keys, invite users, delete data, or change settings.
- Account email and user-specific values were redacted or omitted from docs.

### Verification

- Ran `node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs`.
- Result: 30 tests passed, 0 failed.
- Ran `git diff --check`; only existing LF-to-CRLF warnings were reported.
- Confirmed `.env.local` is ignored by `.gitignore`.
- Ran targeted scans for emails, user handles, real API-key assignments, bearer tokens, and cookie/token assignments in A3-owned files.
- New authenticated-frontend docs did not contain the account email, username, key, cookie, or token values.
- A broader scan still matches an old intentional fake fixture string shaped like `ashr_live_...`; it is synthetic test content, not a real Ashr secret.

### Remaining unknowns

- Populated dataset detail, run detail, case detail, expected-vs-actual, and trace timeline were not visible because the observed account had no UI-visible datasets/runs.
- Native backend failure-class evidence was checked later with a real failed run; frontend failure labels still require a UI-visible populated run.
- Signed media URL behavior is still confirmed for one dataset action field name only, not full audio/image/video UI rendering.

### Next top 3

1. Get one UI-visible populated run and observe the populated run/case detail frontend.
2. Add a request provenance panel to A3 using confirmed request API fields.
3. Decide whether to keep Trust/Usage as documentation-only product inspiration or add a minimal local mock panel later.

## 2026-07-06 - Request Provenance dashboard closeout

### Goal

Continue the P3/A3 product-logic goal by turning confirmed real Ashr request fields into a visible dashboard/report feature.

### Implemented

- Added `summarizeRequestProvenance()` in `services/report/report_builder.mjs`.
- The summary supports direct request samples, `sample`, `get_request`, `list_requests`, and `calls.*.sample` shapes.
- Preserves only safe request metadata:
  - request status
  - actual/estimated duration
  - accepted input types
  - generation output flags
  - test strategy if not redacted
  - tool count
  - failure-present flag
- Added `request_provenance` to JSON report export.
- Added `Request Provenance` section to Markdown export.
- Added dashboard Request Provenance panel for the P3 media source.
- Dashboard now loads `fixtures/a3/p3/ashr_request_detail_sample.redacted.json` when `source=p3-media`.
- Added report-builder and dashboard wiring tests.
- Updated:
  - `docs/a3/acceptance_checklist.md`
  - `docs/a3/a3_dashboard_polish.md`
  - `docs/a3/p3_a3_mvp_recommendations.md`

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

- Started local static server at `http://127.0.0.1:5173`.
- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Request Provenance rendered:
  - status `failed`
  - accepted inputs `audio, file, image, text`
  - generation outputs `generate_audio, generate_files, generate_images`
  - tool count `1`
  - redacted strategy
  - failure noted `yes`
- Browser console warnings/errors: none.
- Screenshot saved: `docs/screenshots/a3-dashboard-request-provenance.png`.

### Safety

- No live Ashr API calls.
- No `.env.local` reads or writes.
- No key, cookie, token, or account information added.
- Uses only committed redacted P3 request fixture data.

### Next top 3

1. Get one UI-visible populated run to verify frontend run/case detail and failure labels.
2. Observe populated run detail, case detail, trace/timeline, and expected-vs-actual pages.
3. Confirm signed media URL behavior across audio, image, file, and video before rendering live links.

## 2026-07-06 - Failed run probe and Chrome frontend recheck

### Goal

Continue real Ashr API + frontend product calibration after the user confirmed Chrome login worked. Close the highest-value remaining evidence gap: use a real failed run, if present, to verify failure fields without mutating Ashr data.

### Safety

- Confirmed `.env.local` exists and is ignored by `.gitignore`.
- Loaded `ASHR_API_KEY` into the process only for read-only probe commands.
- Did not print the key.
- Did not read or save cookies, browser storage, tokens, or raw account details.
- Did not submit forms, create datasets, create keys, invite users, or change settings.
- Did not save authenticated frontend screenshots.

### Read-only Ashr API calls

Saved new sanitized fixtures:

- `fixtures/a3/p3/ashr_failed_run_probe.redacted.json`
- `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`
- `fixtures/a3/p3/ashr_request_probe.redacted.json`
- `fixtures/a3/p3/ashr_failed_request_detail.redacted.json`

Confirmed fields from the failed run:

- `run.result.status == "failed"`
- aggregate passed/failed counts
- `run.result.cases[]`
- `cases[].status == "failed"`
- `cases[].grade.label == "failed"`
- `cases[].grade.passed == false`
- `cases[].grade.score`
- `cases[].grade.reason`
- `cases[].grade.metrics.text_match`
- `cases[].grade.metrics.tool_match`
- `cases[].observations[]`

Important conclusion:

- The real failed run did not expose a named backend `failure_class` field.
- A3 should continue deriving failure clusters from confirmed fields such as `grade.metrics`, expected/actual, and tool-call evidence.
- In this sample, A3 mapped the failed cases into `bad_final_response` and `missing_required_tool`.

Confirmed fields from the failed request:

- `request.request_status == "failed"`
- `request.request._failure` exists
- `request.request._failure.error` exists after redaction

A3 should treat failed requests as request-provenance evidence, not as case-level judge results.

### Authenticated frontend recheck

Connected to the user's logged-in Chrome through local CDP and observed Lab pages read-only:

- `?tab=analysis`: Datasets page loaded successfully, but showed 0 UI-visible datasets and `No datasets match your filters.`
- `?tab=analytics`: loaded successfully, but showed 0 agents, 0 datasets, 0 graded runs, and not enough data.
- `?tab=trust`: loaded successfully and showed the run-tests-first empty state.
- `?tab=agents`: loaded successfully and showed no agents.
- `?tab=folders`: loaded successfully and showed no folders.
- `?tab=usage`, `?tab=api-keys`, and `?tab=team` were observed earlier in the same authenticated session; no key values or account-specific values were saved.

Frontend conclusion:

- The API has usable run/request evidence, including a failed run.
- The Lab frontend account still has no UI-visible populated dataset/run to open.
- Populated run detail, case detail, expected-vs-actual, and trace/timeline frontend pages remain unobserved.

### Mapper update

- Updated `services/report/p3_ashr_mapper.mjs` so `extractAshrRuns()` can consume API probe wrapper shapes such as `response.run` and `response.runs`.
- Added a mapper test using `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`.
- Confirmed the failed-run fixture maps to one A3 run and three failed A3 cases.

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

### Next top 3

1. Find a UI-visible populated Lab run or dataset so A3 can observe real frontend run/case detail pages.
2. Confirm signed media URL behavior across audio, image, file, and video before rendering live signed links.
3. Keep native failure class as derived in A3 unless a future Ashr sample exposes a named backend `failure_class`.

## 2026-07-06 - API/frontend visibility comparison

### Goal

Clarify why the Lab frontend still shows empty states even though real API probes can return datasets, runs, and requests.

### Read-only API probes

Saved sanitized fixtures:

- `fixtures/a3/p3/ashr_dataset_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_run_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_request_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_failed_run_dataset_detail.redacted.json`

Confirmed API object counts:

- datasets: 3
- runs: 2
- requests: 5

Confirmed API fields:

- dataset fields: `id`, `name`, `dataset_type`, `dataset_source`, `request_id`, `run_count`, `created_at`
- run fields: `id`, `dataset`, `result.status`, `result.aggregate_metrics`, `result.cases[]` or `result.tests[]`
- request fields: `id`, `request_name`, `request_status`, `request`, `actual_duration_s`, `estimated_duration_s`
- dataset detail fields: `dataset.dataset_source.dataset_type`, `dataset.dataset_source.runs`, `dataset.dataset_source.total_runs`

### Frontend comparison

Authenticated Chrome/CDP observation still showed:

- Datasets page: 0 UI-visible datasets / no matching datasets.
- Analytics page: 0 agents, 0 datasets, 0 graded runs.
- Trust page: run-tests-first empty state.

### Interpretation

- API data exists and remains usable for A3 calibration.
- The frontend is reachable and authenticated, but does not show those API objects in the current visible pages.
- The cause is not confirmed; possible explanations include filters, workspace visibility, repo scoping, or product separation between API calibration objects and visible Lab artifacts.
- A3 should not guess hidden frontend routes. It should keep using sanitized API fixtures for populated run/case evidence until a UI-visible hosted run is available.

### Documentation

- Added `docs/a3/p3_api_frontend_visibility_gap.md`.
- Linked the visibility gap from `docs/a3/p3_frontend_page_map.md` and `docs/a3/acceptance_checklist.md`.

### Next top 3

1. Ask for or create, with explicit approval only, one UI-visible populated Lab run if frontend detail pages must be verified.
2. Keep A3 populated run/case behavior backed by sanitized API fixtures.
3. Confirm signed media URL behavior per media type before rendering live media links.

## 2026-07-06 - Frontend session-expired network probe

### Goal

Check whether the currently connected Chrome session can still fetch Lab data from the frontend.

### Observation

Read-only Chrome/CDP observation found:

- The Lab page now shows sign-in UI.
- Visible text includes `Your session has expired. Please sign in again.`
- Frontend POST requests to `api.ashr.io/testing-platform-api` returned `401`.

Saved sanitized fixture:

- `fixtures/a3/p3/ashr_frontend_session_expired_network.redacted.json`

### Safety

- Did not save request headers.
- Did not save cookies.
- Did not save tokens.
- Did not save response bodies.
- Did not save screenshots.
- Did not submit sign-in forms.

### Interpretation

- The browser frontend session has expired and needs fresh manual login before further frontend detail observation.
- This does not invalidate local API probes through `.env.local`; those are a separate credential path.
- A3 should keep using sanitized API fixtures for populated run/case evidence until a UI-visible hosted run can be observed in a fresh logged-in frontend session.

### Next top 3

1. Ask the user to sign in again only when we are ready to observe frontend run/case detail pages.
2. Continue treating redacted API fixtures as authoritative for populated A3 mapping.
3. Avoid guessing hidden frontend routes while the frontend session is expired.

## 2026-07-06 - Signed media URL coverage audit

### Goal

Turn the remaining signed-media uncertainty into a precise evidence statement: which media types have confirmed `signed_url` fields, and whether A3 can safely render live media links.

### Method

Scanned the redacted local P3 fixtures under `fixtures/a3/p3` for:

- `signed_url`
- `output_path`
- `action_type`
- media request flags such as `generate_audio`, `generate_files`, `generate_images`, and `generate_videos`

No raw URL values were printed or saved.

### Evidence saved

- `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`
- `docs/a3/p3_signed_media_url_coverage.md`

### Findings

- 18 redacted P3 fixture files scanned.
- 2 `signed_url` keys found.
- Both `signed_url` keys were nearest to file-like actions.
- 0 audio `signed_url` samples found.
- 0 image `signed_url` samples found.
- 0 video `signed_url` samples found.
- `output_path` evidence exists for file and audio.
- image/video appear in accepted-input and generation flags, but not as concrete signed URL samples.

### A3 decision

- Preserve `signed_url` metadata only in redacted form.
- Do not render live signed links yet.
- Do not infer audio/image/video signed URL behavior from file-only evidence.
- Keep Media Evidence focused on media type, action tags, output path presence, audio tags, VM stream evidence, and known gaps.

### Next top 3

1. Get sanitized audio signed URL evidence.
2. Get sanitized image/video signed URL evidence if those features are in scope.
3. Confirm signed URL expiry/access behavior before any live link rendering.

## 2026-07-06 - Chinese P3/A3 handoff summary

### Goal

Create a beginner-friendly handoff note that explains current A3/P3 status, evidence, remaining external gaps, and what to say if the group lead asks.

### Added

- `docs/a3/p3_status_handoff_cn.md`

### Content

The handoff explains:

- what the Ashr clone project is doing
- what A3 owns
- which dashboard/report pieces are already done
- which real Ashr API fields were confirmed
- what the failed-run probe proved
- why A3 derives failure class
- what was observed in the real Ashr frontend
- why the frontend still needs fresh login and a UI-visible populated run
- why live signed media links should not be rendered yet
- what remains externally blocked

### Decision

Use this as the short human-facing handoff for student/team communication. Keep the more detailed technical evidence in the existing P3 mapping, visibility-gap, signed-media, and worklog docs.

## 2026-07-06 - Frontend relogin observation checklist

### Goal

Prepare the next frontend calibration pass so it can start safely after the user manually logs into Ashr Lab again.

### Added

- `docs/a3/p3_frontend_relogin_observation_checklist.md`

### Checklist scope

The checklist defines:

- preconditions before starting observation
- secret-safety rules
- priority order for Datasets, Dataset detail, Run detail, Case detail, Trace, Expected vs Actual, Media Evidence, Report/Trust
- evidence files to update
- stop conditions such as `401`, captcha, password prompt, or visible secrets
- minimum success standard for the next frontend pass

### Decision

Do not attempt more frontend observation while the browser session is expired. Use this checklist after fresh manual login and only proceed read-only.

## 2026-07-06 - Frontend relogin top-level confirmation

### Goal

Re-check the real Ashr Lab frontend after the user manually logged in again, and confirm whether deeper run/case UI calibration can continue.

### Method

- Connected read-only to the user's Chrome through the local CDP debugging port.
- Did not save cookies, headers, tokens, response bodies, screenshots, email, or account-specific values.
- Opened only safe top-level Lab tabs: Usage, Datasets, Analytics, Agents, Folders, and Trust.
- Did not open API key values, invite/team actions, create flows, or submit forms.

### Evidence saved

- `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`

### Findings

- Fresh frontend login is valid.
- Frontend Lab requests returned `200`, not the earlier `401`.
- `?tab=usage` shows quota modules for Images, Audio, and Files.
- `?tab=analysis` loads the Datasets console with filters for Type, Agent, Creator, Status, Runs, time, Sort, and Group.
- After a longer wait, Datasets showed `0` and `No datasets match your filters.`
- `?tab=analytics` shows the real product analytics modules: Agents, Datasets, Graded runs, Overall pass rate, Run volume, Pass rate over time, Runs by agent, and Pass rate by agent.
- Analytics still showed 0 agents, 0 datasets, and 0 graded runs.
- Agents and Folders also showed empty states.
- Trust showed the public trust/certificate concept, but still said tests must be run before anything can be certified.

### Conclusion

This pass removes the stale blocker of "frontend session expired." The current blocker is now narrower: the authenticated frontend account has no UI-visible populated dataset/run, so run detail, case detail, expected-vs-actual, trace/timeline, and native frontend failure labels still cannot be observed directly.

### A3 decision

- Keep using sanitized real API fixtures as the evidence source for populated run/case/trace behavior.
- Use the real frontend only for confirmed product-console navigation, empty states, analytics concepts, usage/quota concepts, and trust/report inspiration.
- Do not invent hidden frontend detail routes or native failure labels.

## 2026-07-06 - Media usage/quota calibration and A3 panel

### Goal

Continue A3 Product Console / UI Workflow Commercial Growth with the highest-ROI media-focused enhancement: connect real Ashr media/usage evidence to the dashboard and report workflow.

### ROI decision

Selected: Usage / Quota + Media calibration panel/report enhancement.

Why:

- It directly addresses the media direction requested for the next iteration.
- The official frontend has visible Images, Audio, and Files quota modules.
- The frontend revealed concrete usage functions: `get_usage` and `billing_get_status`.
- Direct API-key calls to those functions returned OAuth-only 403 responses, which is important product evidence for A3.
- The implementation is small and stays inside A3-owned dirs.

Backlog candidates:

- Full media preview/link rendering: still blocked because audio/image/video signed URL behavior is not confirmed.
- Full frontend run/case detail replication: still blocked by missing UI-visible populated run.
- Trust publishing flow: product inspiration only, not student MVP scope.

### Read-only Ashr API calls

L0 read-only calls completed:

- `init`
- `list_datasets`
- signed-url `list_datasets` probe with `include_signed_urls=true`
- `list_requests`
- `list_runs`
- 3 `get_dataset`
- 5 `get_request`
- 2 `get_run`
- `get_usage`
- `billing_get_status`

Results:

- Datasets observed: 3
- Requests observed: 5
- Runs observed: 2
- `signed_url` paths observed: 2
- `get_usage`: 403, OAuth-only for API key
- `billing_get_status`: 403, OAuth-only for API key

Saved redacted evidence:

- `fixtures/a3/p3/ashr_media_api_calibration.redacted.json`
- `fixtures/a3/p3/ashr_media_run_case_sample.redacted.json`
- `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`

### Official frontend observation

Authenticated Chrome/CDP observation confirmed:

- Usage page path: `/?tab=usage`
- Visible media quota channels: Images, Audio, Files
- Frontend Usage functions: `get_usage`, `billing_get_status`
- Datasets functions: `list_datasets`, `list_requests`, `list_folder_memberships`
- Analytics functions: `list_agents`, `list_datasets`
- Trust functions: `get_trust_certificate_status`, `preview_trust_certificate`

Saved redacted frontend evidence:

- `fixtures/a3/p3/ashr_frontend_usage_workflow.redacted.json`
- `docs/a3/p3_media_frontend_notes.md`

### Implemented

- Added `summarizeUsageQuota()` in `services/report/report_builder.mjs`.
- JSON export now includes `usage_quota`.
- Markdown export now includes a `Usage / Quota` section.
- Dashboard Usage / Quota panel now shows:
  - media channels: audio, files, images
  - frontend functions: `billing_get_status`, `get_usage`
  - API-key access: no
  - OAuth-gated functions
  - A3 decision to show frontend-confirmed quota state
- Print/PDF report preview now includes Usage / Quota.

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

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Usage / Quota text renders.
- Confirmed no horizontal overflow.
- Saved screenshot: `docs/screenshots/a3-dashboard-usage-quota-media.png`.

### Safety

- Did not print or save the real API key.
- Did not save browser token values, headers, cookies, response bodies, emails, or account values.
- Did not create, mutate, delete, publish, invite, or generate real Ashr objects.
- Signed URL values are represented only as `[REDACTED_SIGNED_URL]`.

### Next top 3

1. Get one UI-visible populated hosted run to observe real run/case/trace/media preview pages.
2. Get sanitized audio/image/video signed URL samples before any live link rendering.
3. If approved, design a minimal L1 dry-run plan for one tiny frontend-visible demo request/run.

## 2026-07-06 - Official dashboard gap comparison

### Goal

Use already collected official Ashr frontend/API calibration evidence to compare A3 with the real product and improve the local A3 MVP in the safest area.

### Product comparison

A3 already matches the core evaluation-review loop:

- runs
- case detail
- expected vs actual
- trace timeline
- tool-call diff
- failure clusters
- media evidence
- report export

The official product has broader cloud-console areas:

- Datasets
- Agents
- Folders
- Analytics
- Usage
- Trust
- API Keys
- Team

The student MVP should copy the navigation and evidence-review ideas, but should not copy account administration, API-key management, billing, OAuth login, team invites, hosted mutation flows, or public trust publishing.

### Implemented

- Added `docs/a3/p3_official_dashboard_gap_analysis.md`.
- Added `summarizeOfficialAshrGap()` in `services/report/report_builder.mjs`.
- Added dashboard panel `Official Ashr Gap`.
- Added report JSON field `official_ashr_gap`.
- Added Markdown/print report section `Official Ashr Gap`.
- Added tests for dashboard wiring and report-builder output.

### Safety

- No new real Ashr API calls were required.
- No browser cookies, tokens, headers, emails, account values, keys, or signed URLs were saved.
- No real Ashr objects were created, deleted, published, invited, or mutated.

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
- Confirmed the `Official Ashr Gap` dashboard panel renders.
- Confirmed the print/PDF report preview includes `Official Ashr Gap`.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-gap.png`.

## 2026-07-06 - Media readiness and cloud console polish

### Goal

Continue the P3/A3 product-console iteration by improving media handling and safely mimicking official Ashr cloud/admin surfaces.

### Implemented

- Added product-level `Media Readiness`.
- Added signed URL safety summary using redacted coverage evidence.
- Added `Cloud Console Shell` as a read-only status map for:
  - auth session
  - workspace / tenant
  - datasets / runs
  - usage / billing
  - API keys
  - team
  - trust / report
  - cloud mutations
- Added UI polish:
  - sidebar brand mark
  - status chips
  - Media and Cloud Shell nav links
  - clearer badges and panel states
- Added report fields:
  - `media_readiness`
  - `cloud_console_shell`
- Added Markdown/print report sections:
  - `Media Readiness`
  - `Cloud Console Shell`
- Added documentation: `docs/a3/p3_media_cloud_console_polish.md`.

### Safety boundary

The dashboard mimics the product shape only. It does not implement:

- real login/OAuth
- API-key management
- team invites
- billing changes
- public trust publishing
- create/delete/publish cloud mutations
- live signed URL rendering

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
- Confirmed `Media Readiness` renders with media channel and signed URL safety state.
- Confirmed `Cloud Console Shell` renders with auth/workspace/API-key/team/billing/trust/cloud-mutation boundaries.
- Confirmed print/PDF report preview includes both new sections.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-cloud-polish.png`
  - `docs/screenshots/a3-dashboard-cloud-shell.png`

## 2026-07-06 - Media matrix and cloud action guardrails

### Goal

Make the media/cloud polish more explicit for reviewers by showing exact per-channel media decisions and exact cloud/admin action boundaries.

### Implemented

- Media Readiness now includes `channel_matrix`.
- Each media channel has:
  - usage observation
  - case evidence count
  - output path status
  - signed URL status
  - preview policy
  - decision text
- Cloud Console Shell now includes `actions`.
- Actions mark safe local flows as enabled and sensitive official-cloud flows as disabled.
- Dashboard renders:
  - `media-channel-matrix`
  - `cloud-action-list`
- Print/PDF report includes both tables.
- Markdown report includes `Cloud Action Guardrails`.

### Safety

This still does not add real login, API-key management, team invites, billing mutations, Trust publishing, hosted dataset creation, cloud deletion, or live signed URL rendering.

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
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-matrix.png`
  - `docs/screenshots/a3-dashboard-cloud-guardrails.png`

## 2026-07-06 - Chrome/CDP official agent wizard crawl

### Goal

Recover from the in-app-browser Google login stall, use an authenticated normal Chrome session to crawl the real Ashr Lab UI, and prepare a minimal official demo agent/dataset draft for A3 calibration.

### What happened

- The Codex in-app browser repeatedly stalled on Google's `gis_transform` page during login.
- A normal Chrome profile was launched with local CDP debugging and the user manually logged into Ashr Lab.
- The authenticated page was confirmed at `https://lab.ashr.io/?tab=analysis`.
- Top-level Lab pages were crawled through Chrome/CDP:
  - Datasets
  - Agents
  - Folders
  - Analytics
  - Usage
  - Trust
  - API Keys
  - Team
- Account-specific values were redacted; no cookies, tokens, API keys, or raw emails were saved.

### Official wizard findings

- The official `New dataset` flow has 8 steps:
  - Basic Info
  - Agent
  - Inputs
  - Tools
  - Context
  - Test Config
  - Behaviors
  - Review
- The wizard supports media input types:
  - text
  - audio
  - conversation
  - file
  - image
  - video
  - website simulation
  - custom schema
- The wizard supports tool definitions with:
  - tool name
  - tool description
  - parameter name
  - parameter type
  - parameter description
  - optional marker
- The wizard supports behavior/rubric-style constraints:
  - tool order
  - response requirements
  - success criteria

### Prepared draft

Filled an official wizard draft to the Review step:

- Dataset: `A3 Refund Demo Dataset`
- Agent: `A3 Refund Demo Agent`
- Domain: `e-commerce`
- Accepted inputs: `text`, `audio`, `file`, `image`
- Tool: `confirm_cancel`
- Parameter: `booking_id`
- Coverage: 5 diverse variations, including multi-input scenarios
- Behavior rule: refund completion must be confirmed through the correct tool call

The final `Generate Test Suite` button was not clicked because it creates real hosted Ashr data. This remains pending explicit user confirmation.

### Evidence

- Added `fixtures/a3/p3/ashr_chrome_agent_wizard_review.redacted.json`.
- Updated `docs/a3/p3_frontend_page_map.md`.
- Updated `docs/a3/p3_frontend_workflow_notes.md`.
- Updated `docs/a3/acceptance_checklist.md`.

### Next

1. If approved, click `Generate Test Suite` in the official Review step.
2. Revisit Agents/Datasets to see whether the generated hosted objects become UI-visible.
3. If a run/case can be generated, observe official expected-vs-actual, tool-call, pass/fail, and media evidence pages.

## 2026-07-06 - Official Generate Test Suite execution

### Goal

Create one real official frontend-visible Ashr dataset/test-suite example after explicit user confirmation, then observe what appears in the official UI.

### User confirmation

The user explicitly confirmed:

```text
确认生成 A3 Refund Demo Dataset / A3 Refund Demo Agent
```

### Action

- Clicked the official `Generate Test Suite` button in the Review step.
- Observed the button enter `Generating...`.
- Observed three Ashr API/network responses with HTTP `200`.
- Waited for generation to settle and reloaded the Datasets page.

### Result

The official frontend showed a new dataset:

- Name: `A3 Refund Demo Dataset`
- Display id: `#00000374`
- Dataset id: `884`
- Frontend path: `?tab=analysis&dataset=884`
- Test cases: 5
- Results: 0
- Runs history: no runs found
- Analytics: dataset count moved to 1, graded runs remained 0
- Agents page: still `No agents yet`

Generated test cases:

- `happy_path_text_valid_booking`
- `pdf_receipt_ocr_split_payment`
- `audio_cutoff_by_two_minutes_exception_request`
- `ui_shows_refund_but_backend_no_tool_call_image`
- `concurrent_requests_tool_timeout_then_processor_failure`

The generated cases cover text, audio, file, and image inputs. They are strong evidence for official dataset/case browsing and media-oriented case metadata, but they are not completed run results yet.

### Read-only API follow-up

Saved redacted evidence:

- `fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_requests.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_datasets.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_agents.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_requests_wait.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_datasets_wait.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_agents_wait.redacted.json`

`get-dataset 884` succeeded and confirmed `dataset_source.total_runs == 5`.

### Safety

- The mutation was limited to the explicitly confirmed `Generate Test Suite` action.
- No API key values were printed or saved.
- No cookies, browser tokens, request headers, emails, or screenshots were saved.
- No API key management, team invite, billing, Trust publishing, or delete action was performed.

### Interpretation

This solves the previous "no real official frontend example" gap for dataset/case definitions. The remaining gap is narrower:

- Still missing: official run execution result.
- Still missing: official frontend pass/fail, score, actual tool calls, trace timeline, and failure reason for this new dataset.

### Next

1. Find the official way to run dataset `884` against an agent.
2. If a run can be produced safely, observe official Results / run detail / case result pages.
3. Map generated dataset case metadata into A3 dashboard/report provenance.

## 2026-07-06 - Official demo run 11925 mapped into A3 dashboard

### Goal

Turn the real frontend-visible `A3 Refund Demo Dataset` into a complete A3 triage example by adding one hosted run result and wiring it into the dashboard as a selectable source.

### Result

- Created a local synthetic run-result payload for dataset `884` with the same five generated refund test cases.
- The synthetic run has 2 passing cases and 3 failing cases.
- Created a hosted Ashr run through the safe A1 API probe path.
- Created run id: `11925`.
- Run status: `failed`.
- Dataset id: `884`.
- Saved redacted evidence:
  - `fixtures/a3/p3/ashr_dataset_884_demo_run_result.synthetic.json`
  - `fixtures/a3/p3/ashr_dataset_884_create_run_plan.redacted.json`
  - `fixtures/a3/p3/ashr_dataset_884_create_run_real.redacted.json`
  - `fixtures/a3/p3/ashr_dataset_884_run_11925_detail.redacted.json`
  - `fixtures/a3/p3/ashr_dataset_884_list_runs_after_create.redacted.json`

### Dashboard wiring

- Added a dashboard data source: `P3 Official Demo 884/11925`.
- The source loads:
  - `fixtures/a3/p3/ashr_dataset_884_run_11925_detail.redacted.json`
  - `fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json`
  - `fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json`
- A3 now maps the official demo to:
  - 1 run
  - 5 cases
  - 2 passed
  - 3 failed
  - 40% pass rate
  - 56.4 average score
  - 100% trace completeness
  - 5 media-evidence cases
  - 5 VM-stream cases
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-official-demo-884-11925.png`

### Mapper updates

- `services/report/p3_ashr_mapper.mjs` now reads official dataset wrappers shaped like `response.dataset`.
- Dataset scenario metadata is joined into run cases for the official `884` sample.
- Dataset media action types are preserved in A3 `media_evidence`, including audio, file, and image channels.
- Output paths stay metadata-only; live signed URL rendering remains blocked by safety policy.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 41
pass 41
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed data source label: `P3 official Ashr demo dataset 884 / run 11925`.
- Confirmed visible counts: 1 run, 5 cases, 40% pass rate, 56.4 average score, 100% trace completeness.

### Remaining limitation

The frontend session expired before the populated official Results/run-detail page could be visually inspected. API evidence confirms the hosted run exists and is retrievable, but the official frontend result page still needs a fresh manual login pass.

## 2026-07-06 - Official frontend relogin check after run 11925

### Goal

Try to directly open the official Ashr frontend for dataset `884` after run `11925` exists, so A3 can compare its local dashboard against the real Results/run-detail UI.

### Action

- Opened `https://lab.ashr.io/?tab=analysis&dataset=884` in the Codex in-app browser.
- Read the page state without entering credentials and without saving cookies/tokens/headers.

### Result

- The page landed on the Ashr sign-in screen.
- Visible copy included:
  - `Sign in to your account`
  - `Continue with Google`
  - `Continue with Microsoft`
- Dataset `884` and run `11925` were not visible in the frontend in this unauthenticated state.
- Saved redacted evidence:
  - `fixtures/a3/p3/ashr_dataset_884_frontend_relogin_needed.redacted.json`

### Updated interpretation

This is no longer a "no real run exists" blocker. The real hosted run exists through API evidence and is already mapped into A3. The remaining work is specifically a frontend visual comparison after manual login.

Next manual step:

1. User signs into Ashr Lab in the browser.
2. Reopen `https://lab.ashr.io/?tab=analysis&dataset=884`.
3. Inspect Results / run detail / case detail / trace UI for run `11925`.

## 2026-07-06 - Authenticated official frontend dataset/case observation

### Goal

After the user restored the logged-in normal Chrome session, directly observe the real Ashr frontend for dataset `884` and compare it against A3's local `p3-official-demo` source.

### Observation

- Connected to the user's authenticated normal Chrome session through local CDP.
- Opened `https://lab.ashr.io/?tab=analysis&dataset=884`.
- Confirmed the official frontend shows:
  - dataset `A3 Refund Demo Dataset`
  - display id `#00000374`
  - `Overview`
  - `Test cases (5)`
  - `Results (0)`
  - generated request status `Completed`
- Opened `Test cases (5)`.
- Confirmed all five generated refund cases are visible with:
  - ordinal
  - title
  - case key
  - description
  - action count
  - tag count
- Opened sample case `happy_path_text_valid_booking`.
- Confirmed official case detail shows:
  - `TEST DETAILS`
  - tags
  - `ACTIONS (4)`
  - actor labels (`User`, `Agent`)
  - content text
  - input/media labels (`TEXT`, `AUDIO`)
  - `Tool Calls (1)`
  - `Back to Tests`
  - `Open Most Recent Run`

### Results / run visibility finding

- Clicking `Open Most Recent Run` still showed:
  - `Runs History`
  - `No runs found`
  - `This dataset hasn't been run yet`
- Direct URL attempt `?tab=analysis&dataset=884&run=11925` returned to dataset overview and did not show run `11925`.
- Official frontend did not show score, pass/fail, expected-vs-actual result, trace result, or failure class for API-created run `11925`.

### Evidence

- Added `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`.
- No screenshots were saved because the page includes account-adjacent UI such as user initials and internal creator id.
- No raw payload/config modal was opened.
- No API key, cookie, token, header, or email was saved.

### Interpretation

A3 now has a clearer product gap:

- Official frontend confirms dataset and generated test-case browsing.
- A3 mirrors this with dataset/case metadata, media evidence, and case detail.
- API-created run `11925` is retrievable and A3 can display it locally.
- Official frontend Results does not list that API-created run, so populated official Results UI parity is blocked by product/API visibility mismatch, not by missing A3 code.

## 2026-07-07 - Official UI-compatible tests run 11926

### Goal

Try another safe path to make a real result object that is closer to what the official Ashr frontend expects. The previous run `11925` used an A1-like `result.cases[]` shape. Frontend bundle and fixture evidence point to the official Results flow reading `run.result.tests[].action_results[]`.

### What changed

- Created a synthetic, redacted, official-UI-shaped result fixture:
  - `fixtures/a3/p3/ashr_dataset_884_demo_run_result.official_ui_tests.synthetic.json`
- The fixture converts the same five refund demo cases into:
  - `result.tests[]`
  - `tests[].test_id`
  - `tests[].action_results[]`
  - user text actions
  - tool-call comparison actions
  - expected vs actual response actions
  - `aggregate_metrics.total_tests`
  - `aggregate_metrics.tests_passed`
  - `aggregate_metrics.tests_failed`
- Ran a dry-run mutation plan:
  - `fixtures/a3/p3/ashr_dataset_884_create_run_ui_tests_plan.redacted.json`
- Created one real Ashr hosted run:
  - run id `11926`
  - dataset id `884`
  - 5 tests
  - 2 pass / 3 fail
  - result status `completed_with_failures`
  - evidence: `fixtures/a3/p3/ashr_dataset_884_create_run_ui_tests_real.redacted.json`

### Read-only verification

- `get_run(11926)` succeeded and confirmed `result.tests[]` exists:
  - `fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json`
- `list_runs(dataset_id=884)` now returns both `11926` and `11925`:
  - `fixtures/a3/p3/ashr_dataset_884_list_runs_ui_tests_after_create.redacted.json`
- `list_runs(dataset_id=884, summary_only=true)` also returns both `11926` and `11925`:
  - `fixtures/a3/p3/ashr_dataset_884_list_runs_summary_ui_tests_after_create.redacted.json`
- This is important because the official frontend appears to call `list_runs` with `summary_only: true`.

### Dashboard update

- Updated A3 `p3-official-demo` to read run `11926` instead of `11925`.
- The local dashboard now shows:
  - 1 run
  - 5 cases
  - 2 pass / 3 fail
  - 40% pass rate
  - 56.4 average score
  - 5 media-evidence cases
  - 0 VM stream cases, because the official `tests[]` result does not include the old A1-like `vm_stream` field.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-official-demo-884-11926.png`

### Frontend observation

- The in-app browser was not logged in to Ashr Lab and showed the sign-in page.
- Therefore this round could not visually confirm whether the official Results tab now shows run `11926`.
- The API evidence is stronger than before: run `11926` is not only retrievable by `get_run`, it is also present in the frontend-style `summary_only` run list.

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
- Confirmed data source label references `run 11926`.
- Confirmed metrics: 5 cases, 40% pass rate, 56.4 average score, 5 media cases.

### Current interpretation

The old blocker has changed. It is no longer true that A3 lacks a real run result. A3 now has:

- a real generated dataset `884`
- an old A1-like API run `11925`
- a new official-UI-like API run `11926`
- local dashboard support for `11926`

The remaining proof is visual: refresh the logged-in official Ashr Lab frontend for dataset `884` and check whether Results now lists run `11926`.

## 2026-07-07 - Release Gate commercial growth pass

### Goal

Push A3 toward a commercial release-intelligence workflow, not just a triage dashboard.

### Added capability

A3 now computes a release decision:

- `approve_release`
- `needs_review`
- `block_release`

The release gate considers:

- pass rate
- critical/blocker failures
- unsafe or forbidden-tool failures
- missing required tool failures
- trace completeness
- A2 coverage minimums
- media signed URL safety

### Official demo result

For run `11926`, A3 now says:

- Decision: `Block release`
- Risk score: `70`
- Failed checks: `2`
- Blocks merge: `yes`

This is correct for the demo data because the run only has a 40% pass rate and includes a missing-required-tool failure.

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-release-gate-11926.png`

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 43
pass 43
fail 0
```

## 2026-07-07 - PR Gate workflow and audit bundle commercial pass

### Goal

Extend the Release Gate into a workflow that can be attached to a PR or release review: GitHub check payload, PR comment, waiver policy, reviewer lanes, audit bundle, and incident replay case list.

### Added capability

A3 now builds a `release_workflow` object with:

- GitHub check shape:
  - `Ashr++ Release Gate`
  - `success` / `neutral` / `failure`
  - merge-blocking flag
  - check output title, summary, and text
- PR comment Markdown template.
- Waiver policy:
  - required fields
  - blocked-release exceptional waiver rule
  - expiry maximums
- Reviewer workflow:
  - review state
  - review lanes
  - next actions
- Audit bundle:
  - manifest version
  - redaction policy
  - required and optional artifacts
- Incident replay pack:
  - top-risk failed case ids
  - `failed_cases_first` mode

### API calibration note

No new Ashr hosted mutation was performed in this pass. The workflow is built on the existing redacted official-demo evidence for dataset `884` / run `11926`. This keeps the round focused on release workflow packaging without creating duplicate hosted runs.

### Artifacts

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

### Current interpretation

A3 is now closer to an enterprise release-control surface. It still does not call the GitHub Checks API or persist approvals, but it has the data contract and UI/report surfaces needed for the next implementation step.

## 2026-07-07 - Gate CLI contract and hashed audit manifest

### Goal

Create the local command contract for a future CI/PR release gate.

### Added capability

A3 now has a command-shaped gate entrypoint:

```text
node services/report/a3_gate_cli.mjs --runs fixtures/a3/mock_run_results.json --grades fixtures/a3/mock_grade_results.json --coverage fixtures/a2/results/a2_g3_coverage_report.json --thresholds fixtures/a3/release_gate_thresholds.json --release-version local-mock-commercial-gate --source a3-local-mock --json
```

The output includes:

- `schema_version: a3.gate_cli.v1`
- dashboard summary
- release gate
- release workflow
- GitHub check payload
- waiver policy
- reviewer workflow
- incident replay cases
- audit manifest
- SHA-256 hashes for input files
- exit-code hint for merge blocking
- workspace-relative artifact paths
- `--strict-exit` for CI
- `--no-fail` for local report generation

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
  - `services/report/report_builder.mjs`
- Fixture:
  - `fixtures/a3/release_gate_thresholds.json`
  - `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Docs:
  - `docs/a3/p3_gate_cli_growth_2026_07_07.md`

### API calibration note

This pass did not create new live Ashr API data. It packages existing A3/A2/P3 evidence into a CI-consumable local artifact. No API key, token, cookie, email, header, or live signed media URL was printed or saved.

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

### Current interpretation

A3 now has the contract needed for a GitHub Action or PR check. It is not yet a live GitHub required check, but the payload, evidence hashes, and tests are in place.

### Follow-up hardening

- Added CLI output file support:
  - JSON report
  - Markdown report
  - GitHub Check Run payload
  - PR comment Markdown
- Added GitHub Check annotations for the top-risk cases.
- Added lightweight redaction scrubber for CLI output.
- Added committed redacted PR artifacts:
  - `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
  - `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`
  - `fixtures/a3/p3/a3_gate_cli_report.redacted.md`
- Expanded focused CLI test coverage to 7 tests.

Updated focused verification:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 7
pass 7
fail 0
```

## 2026-07-07 - GitHub dry-run integration adapter

### Goal

Convert the existing A3 PR gate / gate CLI output into GitHub-shaped dry-run artifacts. This prepares A3 for a future required check without using a live token yet.

### Added capability

A3 now includes:

- `buildGitHubCheckRunRequest()`
  - create-check mode
  - update-check mode
  - explicit `headSha` requirement
  - caller-controlled `detailsUrl`
  - normalized annotations
- `buildPrCommentUpsertPlan()`
  - stable HTML marker
  - create-new-comment mode
  - update-existing-comment mode
  - PR comment body from A3 gate evidence
- `buildGitHubActionWorkflowExample()`
  - workflow showing how a future CI job can call `a3_gate_cli.mjs`
  - artifact upload step
  - local gate enforcement step

### Artifacts

- Code:
  - `services/report/a3_github_integration.mjs`
- Tests:
  - `tests/a3/a3_github_integration.test.mjs`
- Fixtures:
  - `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
  - `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`
- Docs:
  - `docs/a3/p3_github_action_workflow_example.yml`
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

### API calibration note

No live GitHub API call was made. No GitHub token, Ashr key, cookie, or signed URL was read or written. This pass uses existing redacted A3 gate evidence only.

### Current interpretation

A3 now has the dry-run bridge from local release gate to GitHub PR workflow. The remaining work is to add an explicitly approved live writer and required-check deployment path.

## 2026-07-07 - Generated artifact manifest for audit-grade exports

### Goal

Extend the Gate CLI audit trail from input evidence hashes to generated output artifact hashes.

### Added capability

A3 now supports:

- `--output-manifest`
- `a3.generated_artifact_manifest.v1`
- output hash records for:
  - `json_report`
  - `markdown_report`
  - `github_check_run`
  - `pr_comment_markdown`
- content type and byte size per generated artifact
- workspace-relative output paths
- release summary embedded in the manifest
- safety metadata showing the manifest is dry-run compatible and should not contain secret values

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- Docs:
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

### API calibration note

No new Ashr or GitHub API call was made. This pass only uses local redacted A3/A2 fixture evidence and generated local output files. No API key, token, cookie, header, email, or signed media URL was read or saved.

### Current interpretation

This closes one enterprise audit gap: reviewers can now verify that generated report artifacts match the files produced by the Gate CLI. The remaining enterprise gaps are signed manifests, immutable storage, persisted approvals, waiver expiry, and live required-check enforcement.

## 2026-07-07 - File-backed waiver validation

### Goal

Turn the release workflow waiver policy into a local file-backed validation contract.

### Added capability

A3 now supports:

- `--waiver`
- `--generated-at`
- `a3.waiver.v1` waiver request fixture
- `a3.waiver_review.v1` validation output
- waiver file hashing in the audit manifest
- Markdown Waiver Review section

The validator checks:

- schema version
- required waiver fields
- run id
- release version
- environment
- head SHA
- expiry date
- max expiry policy
- required approver roles
- approval record fields
- failed-check coverage
- reviewed artifact hash shape

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixtures:
  - `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`
- Docs:
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

### API calibration note

No live Ashr or GitHub API call was made. This pass uses local redacted A3/A2 evidence and local waiver fixtures only. No API key, token, cookie, header, email, or signed media URL was read or saved.

### Current interpretation

This closes part of the waiver governance gap: A3 can now say whether a local exception file satisfies policy. It still does not persist approvals in a backend, verify reviewer identity against GitHub/SSO, or let a waiver automatically unblock a release.

## 2026-07-07 - File-backed signed approval validation

### Goal

Add a structured approval/sign-off validation layer on top of waiver validation.

### Added capability

A3 now supports:

- `--approval`
- `a3.approval.v1` approval record fixture
- `a3.approval_review.v1` validation output
- approval file hashing in the audit manifest
- Markdown Approval Review section

The validator checks:

- schema version
- approval id
- decision enum
- blocked-release exception decision
- run id
- release version
- environment
- head SHA
- waiver id binding
- signer role/name/timestamp
- co-signer role/name/timestamp
- required signer roles
- reviewed artifact SHA-256 hashes
- separation-of-duties self-approval guardrail

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixtures:
  - `fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json`
- Docs:
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

### API calibration note

No live Ashr or GitHub API call was made. This pass uses local redacted A3/A2 evidence and local approval fixtures only. No API key, token, cookie, header, email, or signed media URL was read or saved.

### Current interpretation

This closes part of the sign-off evidence gap: A3 can now verify that a file-backed approval is scoped to the exact run/release/environment/head SHA and references the waiver/artifacts under review. It still needs cryptographic signatures, durable persistence, and real identity binding before it becomes enterprise-grade approval infrastructure.

## 2026-07-07 - Audit bundle index / root hash / chain-of-custody

### Goal

Close the next enterprise audit gap after generated manifests, waiver validation, and approval validation: bind the release evidence into one verifiable bundle index.

### Added capability

A3 now supports:

- `--output-bundle`
- `a3.audit_bundle_index.v1`
- `bundle_root_hash`
- workspace-safe bundle artifact paths
- source/generated/governance/custody artifact grouping
- custody event hashes with `previous_event_hash`
- local retention metadata and verification command hint

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- Docs:
  - `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_audit_bundle_index_2026_07_07.md`

### API calibration note

No live Ashr or GitHub API call was made in this pass. The work uses existing local A3/A2 fixtures plus redacted waiver/approval records. No API key, token, cookie, header, email, or live signed media URL was read or saved.

### Current interpretation

This turns A3 evidence from "several related files" into "one bundle index with a root hash." It is still local and unsigned, but it gives future enterprise work a clear handle for audit, retention, GitHub artifacts, and management sign-off.

## 2026-07-07 - Audit bundle verifier

### Goal

Turn the bundle root hash into something a reviewer can actually verify from the CLI.

### Added capability

A3 now supports:

- `--verify-index`
- `a3.audit_bundle_verification.v1`
- root hash verification
- artifact hash verification
- artifact byte-size verification
- missing artifact detection
- custody event hash verification
- previous-event hash chain verification
- JSON and Markdown verification reports

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- Docs:
  - `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`

### API calibration note

No live Ashr or GitHub API call was made in this pass. The work verifies local redacted bundle evidence only. No API key, token, cookie, header, email, or live signed media URL was read or saved.

### Current interpretation

This makes A3's audit bundle useful after export. A customer or reviewer can run verification and get a pass/fail answer instead of manually checking every JSON file.

## 2026-07-07 - Official frontend mirror clean-room integration

### Goal

Fold the offline Ashr frontend mirror into P3 calibration as a clean-room product map.

### Added capability

A3 now summarizes the mirror into:

- official navigation parity
- official API method group parity
- visible UI label confirmation
- copy / partial / future / out-of-scope decisions
- safety flags for official source, secrets, cookies, tokens, and signed URLs

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Fixture:
  - `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json`
- Docs:
  - `docs/a3/p3_frontend_mirror_analysis_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-official-frontend-mirror.png`

### API calibration note

No live Ashr API call was made in this pass. The work uses the offline redacted mirror summary only. No API key, token, cookie, header, email, raw signed media URL, or official source file was committed.

### Current interpretation

This turns the frontend mirror from "we have a zip" into a dashboard/report-visible product reference. A3 can now explain which official Ashr pages and API groups it is copying, partially copying, deferring, or intentionally excluding.

## 2026-07-07 - Release War Room

### Goal

Create the first money-grade Release War Room layer on top of Release Gate, PR Gate, audit bundle, incident replay, media readiness, usage/quota, and official frontend parity.

### Added capability

A3 now supports:

- `a3.release_war_room.v1`
- `summarizeReleaseWarRoom()`
- dashboard `Release War Room` panel
- JSON export field `release_war_room`
- Markdown section `Release War Room`
- print/PDF `Release War Room` section
- redacted official-demo War Room fixture for dataset `884` / run `11926`

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- Docs:
  - `docs/a3/p3_release_war_room_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_release_war_room_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-release-war-room.png`

### API calibration note

No live Ashr API call was made in this pass. The fixture was generated from existing redacted official demo evidence. No key, token, cookie, email, raw signed media URL, or official source file was saved.

### Current interpretation

This makes A3 feel less like an eval viewer and more like an agent release command center. The current official demo War Room says `no_go`, revenue risk score `93`, merge blocked, waiver required, and audit evidence required.

## 2026-07-07 - Official parity roadmap and media queue

### Goal

Convert official frontend mirror evidence and media calibration evidence into dashboard-visible reviewer workflow.

### Added capability

A3 now supports:

- dashboard `Official Parity Roadmap` panel
- `official_parity_roadmap` JSON export field
- Markdown `Official Parity Roadmap` section
- print/PDF `Official Parity Roadmap` section
- Media Readiness `Media Evidence Queue`
- report-center copy that names parity roadmap as part of the release evidence packet

### A1/A2 calibration note

This pass re-ran A3 tests over:

- A1-style generated run/tool-call/trace fixture paths
- A2 G3 grade results
- A2 G3 coverage report
- P3 Ashr mapper output for real redacted run shapes

The goal is to keep A3 attached to A1 runner output and A2 judge output instead of becoming a standalone dashboard mock.

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_official_parity_media_queue_2026_07_07.md`
- Screenshots:
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

### API calibration note

No live Ashr API call was made in this pass. The work uses existing redacted P3 Ashr fixtures, the official frontend clean-room summary, and local A1/A2-derived fixtures. No API key, token, cookie, email, raw signed media URL, or official source file was saved.
