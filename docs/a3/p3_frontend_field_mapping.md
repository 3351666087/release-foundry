# P3 Frontend Field Mapping

Status legend:

- `confirmed-api`: confirmed in redacted real Ashr API sample.
- `confirmed-ui`: confirmed in direct authenticated Lab UI observation.
- `confirmed-prior-ui`: confirmed in prior logged-in UI notes, not directly scraped this round.
- `derived`: A3 computes the field from confirmed data.
- `blocked-ui`: direct UI confirmation is still blocked.
- `unknown`: not enough evidence.

| Local A3 field | Real Ashr API field | Real frontend field/page | Purpose | Confirmed | A3 needs |
|---|---|---|---|---|---|
| `run_id` | `run.id`, `run.result.run_id` | Runs / Run detail | One execution run | confirmed-api | Yes |
| `dataset_id` | `run.dataset`, `dataset.id` | Datasets / Runs | Evaluation grouping | confirmed-api | Yes |
| `case_id` | `case.case_id`, `test.test_id`, or dataset `run_id` | Run detail case row | Single test/case | confirmed-api | Yes |
| `scenario_id` | dataset `dataset_source.runs.*.run_id` or local fallback | Dataset detail / Run detail | Scenario identity | confirmed-api | Yes |
| `trace_events` | `run.result.cases[].observations[]`, `action_results[]`, or observability traces | Trace/timeline area | Execution timeline | derived / blocked-ui | Yes |
| `tool_calls` | `grade.expected.tool_calls`, `grade.actual.tool_calls`, `action_results[].tool_calls[]` | Expected vs Actual / Tool detail | Tool-call evidence | confirmed-api | Yes |
| `expected` | `grade.expected`, `actions[].expected_response`, `tool_calls[].expected` | Expected panel | Expected behavior/result | confirmed-api | Yes |
| `actual` | `grade.actual`, `actual_response`, actual tool calls | Actual panel | Agent output/result | confirmed-api | Yes |
| `score` | `grade.score`, `case.score`, `semantic_similarity` fallback | Score/pass-fail area | Numeric quality signal | confirmed-api | Yes |
| `passed` | `grade.passed`, aggregate pass counts | Pass/fail badge | Case status | confirmed-api | Yes |
| `failure_reason` | failure/reason fields where present; derived summary otherwise | Failure detail | Explain why failed | confirmed-api for some shapes / derived | Yes |
| `failure_class` | no stable native field confirmed; A3 derives `primary_failure_class` | Failure cluster/filter | Group failures | derived | Yes |
| `media_evidence` | `action_type`, `action_tags`, `output_path`, `signed_url`, `audio_tags`, `vm_stream` | Media evidence/detail | File/audio/image/video proof | confirmed-api | Optional but high value |
| `request_status` | `request.request_status` | Requests page/detail | Generation lifecycle | confirmed-api | Optional |
| `usage_quota` | unknown API field; UI labels `Usage`, `Images`, `Audio`, `Files` | Usage page, `?tab=usage` | Consumption/limits | confirmed-ui / unknown API | Optional |
| `analytics_summary` | derived from run/dataset/pass-rate API fields | Analytics page, `?tab=analytics` | Product-level health view | confirmed-ui / derived | Optional |
| `trust_report` | likely derived from frozen run/pass-rate metrics | Trust page, `?tab=trust` | Public certificate/report concept | confirmed-ui / unknown API | Later |
| `dataset_request_wizard` | request/dataset creation API fields | New Dataset modal | Upstream dataset generation flow | confirmed-ui | No, provenance only |
| `observability_trace` | `list_observability_traces` when feature enabled | Observability/trace page | Production traces | blocked by feature flag | Later |

## Current Round Evidence

- `init`, `health_check`, `list_agents`, `list_datasets`, `get_dataset`, `list_runs`, `get_run`, `list_requests`, `get_request`, and signed-url dataset probes succeeded.
- `list_observability_traces` failed because the account does not have observability enabled.
- `get_run` returned a direct run object with `result.cases[]`.
- The redacted run sample confirms expected/actual, score, pass/fail, failure-like fields, and tool-call fields.
- A 2026-07-06 failed-run probe confirms `run.result.status == "failed"`, `cases[].status`, `cases[].grade.passed`, `cases[].grade.score`, `cases[].grade.reason`, and `cases[].grade.metrics`.
- The failed-run probe did not expose a named native `failure_class`; A3 derives `primary_failure_class`.
- The signed-media probe confirms a dataset action field named `signed_url`; its value is redacted.

## Frontend Confirmation Caveat

The earlier authenticated Edge/normal Chrome attempts were blocked by browser URL safety checks. On 2026-07-06, direct UI content extraction succeeded through an isolated Chrome profile connected over local CDP.

Confirmed authenticated frontend labels:

- Datasets: `?tab=analysis`, with search, Type/Agent/Creator/Status/Runs/time filters, pinned-only, sort, and group.
- Agents: `?tab=agents`, empty-state list.
- Folders: `?tab=folders`, search and `New folder`.
- Analytics: `?tab=analytics`, Agents, Datasets, Graded runs, Overall pass rate, Run volume, Pass rate over time, Runs by agent, Pass rate by agent.
- Usage: `?tab=usage`, Images, Audio, Files quota counters.
- Trust: `?tab=trust`, public trust page / certificate concept.
- API Keys: `?tab=api-keys`, key-management instructions only; no key values saved.
- Team: `?tab=team`, team management concept; account-specific values not saved.
- New Dataset modal: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.

Still unconfirmed in direct frontend because the observed account had no populated UI runs:

- run detail path
- case detail path
- trace timeline page structure
- native frontend failure-class label

Current browser-session caveat:

- An earlier Chrome/CDP network probe showed the Lab browser session had expired.
- After the user manually logged in again, a fresh read-only pass confirmed top-level Lab pages and frontend API calls returned `200`.
- The fresh logged-in UI still showed 0 visible datasets and 0 graded runs.
- Further frontend field confirmation requires one UI-visible populated hosted run, not just a valid login.
