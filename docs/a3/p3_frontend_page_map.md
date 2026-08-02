# P3 Frontend Page Map

## Scope

This page map records what A3 can safely infer from:

- the current read-only ReleaseFoundry API calibration in `fixtures/a3/p3/releasefoundry_frontend_api_objects.redacted.json`
- the current signed-media probe in `fixtures/a3/p3/releasefoundry_media_url_sample.redacted.json`
- the current redacted run detail sample in `fixtures/a3/p3/releasefoundry_run_trace_sample.redacted.json`
- the current failed-run probe in `fixtures/a3/p3/releasefoundry_failed_run_detail.redacted.json`
- the current frontend session-expired network probe in `fixtures/a3/p3/releasefoundry_frontend_session_expired_network.redacted.json`
- the API/frontend visibility comparison in `docs/a3/p3_api_frontend_visibility_gap.md`
- prior logged-in lab observations recorded in A1/A3 docs

Direct Windows automation of the already logged-in Edge/normal Chrome tabs was stopped by the browser-control safety layer because it could not verify the current browser URL with enough confidence. On 2026-07-06, the user logged into an isolated Chrome profile launched with a local CDP debugging port, which allowed direct read-only observation of the authenticated Lab UI. No screenshots, cookies, tokens, or account-specific values were saved.

## Page Map

| Page | Path | Evidence | Purpose | Core Modules | Fields / Signals | A3 MVP Copy |
|---|---|---|---|---|---|---|
| Lab Analysis | `https://app.releasefoundry.example/?tab=analysis` | Authenticated Chrome/CDP observation; API probes | Main product console for evaluation artifacts | Datasets, Runs, filters, `New dataset` | Current UI showed 0 visible datasets; API confirms runs/requests exist separately | Yes: A3 should keep one console shell with datasets, runs, triage, and report |
| Datasets | Lab analysis tab or dataset list | API verified | Group generated scenarios/tests | Dataset list, dataset detail, generated run/storyboard source | `dataset.id`, `dataset.name`, `dataset_type`, `dataset_source.runs`, `run_count`, `created_at` | Yes: A3 should show dataset/source identity and case titles |
| Dataset Detail | Dataset detail route unknown | API verified through `get_dataset` | Inspect scenario/storyboard source | Scenario/run entries, actions, expected responses, media tags | `dataset_source.dataset_type`, `runs.*.title`, `actions[]`, `action_type`, `expected_response`, `audio_tags`, `intent_tags`, `output_path`, `signed_url` | Yes: A3 already joins dataset titles and should keep media/source metadata |
| Runs | Lab analysis tab or run list | API verified through `list_runs` | Show execution batches/results | Run table, status, dataset, runner, result summary | `run.id`, `dataset`, `runner`, `result`, `created_at` | Yes: A3 Run List maps directly |
| Run Detail | Run detail route unknown | API verified through `get_run`; not UI-visible yet | Inspect one hosted/local run result | Case list, per-case result, expected vs actual, grade, trace-like evidence | `result.cases[]`, `grade.expected`, `grade.actual`, `grade.metrics`, `grade.passed`, `grade.score`, `tool_calls` | Yes: A3 Case Detail, Expected vs Actual, Tool Call Diff |
| Requests | Request list/detail route unknown | API verified through `list_requests` and `get_request` | Track generation jobs that create datasets | Request table/detail, status, duration, request config | `request_status`, `request_name`, `actual_duration_s`, `estimated_duration_s`, `request`, `request_input_schema`, `accepted_inputs`, generation flags | Optional: A3 can show request provenance later |
| Usage | Likely `?tab=usage` | Prior logged-in observation | Track quota and media usage | Usage summary, Images, Audio, Files, Upgrade | Labels observed previously; exact counters not stored | Optional now: A3 already has Usage / Quota known-gap panel |
| Observability / Traces | Unknown | API feature-gated | Production trace/log view | Traces, spans, generations, observations | Current account has `features.observability=false`; `list_observability_traces` failed | Later: keep A3 local trace timeline as fallback |
| Settings / API Keys | Unknown | Public docs only | Manage account/API keys | API key list/revoke, account settings | Not observed in authenticated UI this round | Do not copy for MVP |

## 2026-07-06 Authenticated Lab UI Observation

Observed through an isolated Chrome profile connected over local CDP. Actions were read-only except opening safe navigation tabs and opening the dataset wizard without submitting it.

| Page | Path | Observed Modules | Empty-State / Field Signals | A3 MVP Decision |
|---|---|---|---|---|
| Datasets | `?tab=analysis` | Dataset list, `New dataset`, search, filters | `Type`, `Agent`, `Creator`, `Status`, `Runs`, date, pinned-only, sort, group; current account showed 0 datasets | Copy the list/filter mental model, but A3 should show run/case data rather than a dataset generator |
| Agents | `?tab=agents` | Agent list | Current account showed 0 agents / no agents yet | Keep agent as metadata/filter only for MVP |
| Folders | `?tab=folders` | Folder list, search, `New folder` | Current account showed 0 folders | Skip for MVP unless teams need organization |
| Analytics | `?tab=analytics` | Summary metrics and charts | Agents, Datasets, Graded runs, Overall pass rate, Run volume, Pass rate over time, Runs by agent, Pass rate by agent | A3 already mirrors this with summary metrics, failure clusters, coverage health, and report preview |
| Usage | `?tab=usage` | Quota panel, refresh/upgrade | Images, Audio, Files usage limits | Keep as known-gap/optional panel |
| Trust | `?tab=trust` | Public trust/certificate preview | Public trust page, frozen metrics, run-tests-first empty state, refresh | Good commercial inspiration, but skip for student MVP |
| API Keys | `?tab=api-keys` | Key management instructions and create action | Create key, SDK env var guidance, no keys yet | Do not copy; account/security management is outside A3 |
| Team | `?tab=team` | Team member management | Card/table view, invite user, active member, join date | Do not copy for A3 MVP |
| Settings | modal/menu | Theme and Low Power toggles | No A3 evaluation fields | Do not copy except maybe theme polish |
| New Dataset Wizard | modal on Datasets | 8-step request wizard | Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review; fields include dataset name, description, tags | Do not build full generator; use it to explain upstream dataset provenance |

## Current Direct Frontend Limitation

Current round frontend limits:

- The authenticated account had no datasets, no agents, no folders, and no graded runs in the UI, so run detail, case detail, and populated trace/report pages were not directly visible in the frontend.
- A follow-up API probe still returned populated API objects: 3 datasets, 2 runs, and 5 requests.
- This API/frontend mismatch is documented in `docs/a3/p3_api_frontend_visibility_gap.md`.
- An earlier network probe found the browser session expired: sign-in UI was visible and frontend data fetches returned `401`.
- After the user manually logged in again, a fresh read-only pass confirmed the Lab session was valid and frontend API calls returned `200`.
- The fresh logged-in UI still showed no UI-visible datasets, agents, folders, or graded runs.
- Direct UI observation confirms navigation labels and empty-state/product-console structure.
- API samples remain the stronger evidence for `run.result.cases[]`, expected vs actual, tool calls, score/pass-fail, failure-like fields, failed-run evidence, and signed media URL fields.
- A 2026-07-06 frontend request-body observation confirmed Usage calls `get_usage` and `billing_get_status`; direct API-key calls to those functions returned OAuth-only 403 responses. A3 now treats Usage / Quota as frontend-confirmed but API-key-gated.

Practical next step:

- Get access to or create, with explicit approval only, one UI-visible hosted run with populated cases and revisit the UI to observe run/case/trace pages.

## 2026-07-06 Chrome/CDP Agent Wizard Draft

After the in-app browser repeatedly stalled on Google's `gis_transform` login page, an isolated normal Chrome profile was launched with local CDP debugging and the user manually logged in there. This allowed a deeper authenticated observation of the real Lab UI without saving cookies, tokens, API keys, or raw account values.

Additional evidence:

- `fixtures/a3/p3/releasefoundry_chrome_agent_wizard_review.redacted.json`

The New Dataset wizard was filled up to the final Review step only. The final `Generate Test Suite` cloud action was not clicked.

Observed wizard flow:

| Step | Official UI Purpose | Observed Fields | A3 Relevance |
|---|---|---|---|
| Basic Info | Name the generated dataset | dataset name, description, tags | Report provenance |
| Agent | Define the tested agent | agent name, agent description, optional advanced prompt | Run/case metadata and filters |
| Inputs | Declare accepted input channels | text, audio, conversation, file, image, video, website simulation, custom schema | Media evidence readiness |
| Tools | Define function/tool calls | manual entry, paste JSON, tool name, description, parameters | Tool Call Diff and expected-vs-actual |
| Context | Define test domain and scenario | domain, use case, scenario context, user persona, sample data | Scenario summary and judge context |
| Test Config | Configure generation coverage | variation count, strategy, coverage options, complexity, focus/exclude | Coverage health and run provenance |
| Behaviors | Define success constraints | tool order, response requirements, success criteria | Judge/rubric/pass-fail mapping |
| Review | Confirm before generation | dataset, agent, tools, inputs, config, context | Audit/export summary model |

Prepared demo draft:

- Dataset: `A3 Refund Demo Dataset`
- Agent: `A3 Refund Demo Agent`
- Domain: `e-commerce`
- Accepted inputs: `text`, `audio`, `file`, `image`
- Tool: `confirm_cancel`
- Tool parameter: `booking_id`
- Test strategy: 5 diverse variations with multi-input coverage
- Behavior rule: strict tool order; refund completion must be tool-confirmed

Current state:

- The draft is ready at the official Review step.
- The real cloud generation action is pending explicit user confirmation.
- Once generated, the next observation target is whether the resulting dataset/agent becomes visible in `Datasets` / `Agents`, and whether it can produce a populated run/case/trace detail page.

## 2026-07-06 Post-Generation Observation

After explicit user confirmation, `Generate Test Suite` was clicked for the prepared demo. The official frontend returned to the Datasets page and, after reload, showed a new frontend-visible dataset.

Evidence:

- `fixtures/a3/p3/releasefoundry_after_generate_frontend_summary.redacted.json`
- `fixtures/a3/p3/releasefoundry_after_generate_dataset_884.redacted.json`
- `fixtures/a3/p3/releasefoundry_after_generate_list_requests_wait.redacted.json`
- `fixtures/a3/p3/releasefoundry_after_generate_list_datasets_wait.redacted.json`
- `fixtures/a3/p3/releasefoundry_after_generate_list_agents_wait.redacted.json`

Observed result:

| Area | Result |
|---|---|
| Dataset | `A3 Refund Demo Dataset` |
| Frontend path | `?tab=analysis&dataset=884` |
| Display id | `#00000374` |
| Test cases | 5 |
| Results | 0 |
| Runs history | No runs found |
| Agents page | Still `No agents yet` |
| Analytics | Datasets count moved to 1; graded runs still 0 |

Generated test cases:

| Run id | Title | Inputs / Media | A3 Relevance |
|---|---|---|---|
| `happy_path_text_valid_booking` | Cancel and refund request for recent booking | text, audio | Happy path expected behavior |
| `pdf_receipt_ocr_split_payment` | Refund request with low-quality scanned receipt and split payment | file, audio, text | File/media evidence and OCR ambiguity |
| `audio_cutoff_by_two_minutes_exception_request` | Refund window missed by 2 minutes | audio, text | Audio/noisy input and policy edge case |
| `ui_shows_refund_but_backend_no_tool_call_image` | UI says refund completed but trace has no `confirm_cancel` | text, image, audio, file | Image evidence plus tool-call mismatch |
| `concurrent_requests_tool_timeout_then_processor_failure` | Double refund click, timeout, retry, processor failure | text, audio | Incident/retry/concurrency failure |

Interpretation:

- The real frontend-visible dataset/case example now exists.
- This still is not a completed eval run. `Results (0)` means A3 still needs a run execution before it can observe official pass/fail, score, actual tool calls, failure reason, and trace timeline in the frontend.
- For A3 MVP, the generated dataset is now strong evidence for dataset/case browser, case detail, scenario metadata, media input tags, and tool-call expectation design.

## 2026-07-06 Official Demo Run API Evidence

After the post-generation observation, A3 created and fetched a hosted run result for the generated dataset.

| Object | Value | Evidence |
|---|---|---|
| Dataset | `884` / `A3 Refund Demo Dataset` | `fixtures/a3/p3/releasefoundry_after_generate_dataset_884.redacted.json` |
| Run | `11925` | `fixtures/a3/p3/releasefoundry_dataset_884_run_11925_detail.redacted.json` |
| Cases | 5 | Same five generated refund cases |
| Result | 2 pass / 3 fail | `run.result.passed`, `run.result.failed`, `cases[].grade` |
| A3 source | `p3-official-demo` | `apps/dashboard/index.html?source=p3-official-demo` |

Confirmed through API/redacted fixture:

- `run.result.cases[]`
- `cases[].expected`
- `cases[].grade.actual`
- `cases[].grade.score`
- `cases[].grade.passed`
- `cases[].grade.reason`
- expected and actual tool calls
- observations / trace-like timeline
- dataset-derived media channels: audio, file, image

Still not directly observed in official frontend:

- Populated Results tab for run `11925`.
- Official run detail visual layout.
- Official case detail visual layout.
- Official trace/timeline UI.
- Native official failure-class label, if one exists.

Earlier reason before the authenticated Chrome follow-up:

- The frontend session expired after run creation. A fresh manual login is needed before direct visual inspection of populated official Results pages.
- A follow-up in-app browser visit to `https://app.releasefoundry.example/?tab=analysis&dataset=884` landed on the ReleaseFoundry sign-in page instead of the dataset page.
- Redacted evidence: `fixtures/a3/p3/releasefoundry_dataset_884_frontend_relogin_needed.redacted.json`.

## 2026-07-06 Authenticated Dataset 884 Frontend Observation

After the user restored the logged-in normal Chrome session, dataset `884` was observed directly in the official frontend.

Evidence:

- `fixtures/a3/p3/releasefoundry_dataset_884_official_frontend_observation.redacted.json`

Confirmed official frontend pages:

| Page / State | URL / Path | Confirmed Fields | A3 Copy Decision |
|---|---|---|---|
| Dataset overview | `?tab=analysis&dataset=884` | Dataset name, display id `#00000374`, type, total tests, request status, Overview/Test cases/Results tabs | Copy dataset provenance summary |
| Test cases tab | `?tab=analysis&dataset=884` after `Test cases (5)` | Case ordinal, title, case key, description, actions count, tags count | Copy case browser/list |
| Case detail | `?tab=analysis&dataset=884&run=happy_path_text_valid_booking` | TEST DETAILS, tags, ACTIONS, actor, content, media/input type, Tool Calls, Back to Tests, Open Most Recent Run | Copy case detail and action timeline concepts |
| Results tab | `Results (0)` | Runs History, No runs found, this dataset has not been run yet | A3 should mark official Results visibility as blocked for API-created run `11925` |
| Direct run id URL | `?tab=analysis&dataset=884&run=11925` | Returned to overview; run `11925` not visible | Do not assume API run id is a frontend route |

Important interpretation:

- Official frontend dataset/case browsing is now confirmed.
- Official frontend result browsing for run `11925` is not confirmed because the frontend does not list the API-created run.
- A3's `p3-official-demo` source remains useful because it displays the redacted API run result locally, but it is not a pixel-for-pixel copy of the official Results tab.

## 2026-07-07 API Summary-Visible Run 11926

A3 created one additional official-UI-compatible run after discovering that the official frontend expects `result.tests[].action_results[]`.

Confirmed through redacted API evidence:

| Object | URL / Path | Confirmed Fields | A3 Copy Decision |
|---|---|---|---|
| Run `11926` detail | API `get_run(11926)` | `result.tests[]`, `tests[].test_id`, `tests[].action_results[]`, expected response, actual response, tool-call comparisons, pass/fail-derived score | Use as the default official demo source |
| Dataset `884` summary runs | API `list_runs(dataset_id=884, summary_only=true)` | run ids `11926` and `11925`, `result.tests` present for `11926` | Treat as frontend-style API evidence |
| A3 local dashboard | `apps/dashboard/index.html?source=p3-official-demo` | 1 run, 5 cases, 40% pass rate, 56.4 average score, 5 media-evidence cases | Keep as local reproduction of the result-review workflow |

Still not directly observed in official frontend:

- Whether the official visual Results tab now lists run `11926`.
- Official visual run-detail route for `11926`.
- Official visual expected-vs-actual labels for `11926`.

Reason:

- The in-app browser was logged out during this follow-up and showed the ReleaseFoundry sign-in page.
