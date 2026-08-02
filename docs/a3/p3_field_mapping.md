# P3 Field Mapping

Status legend:

- `verified`: confirmed by local API smoke sample or direct SDK model.
- `probable`: present in SDK docs/artifact but not yet seen in this account data.
- `derived`: not a native platform field in the sample; A3 calculates it from verified fields.
- `unknown`: not enough evidence yet.

## Summary mapping

| Local A3 field | Real ReleaseFoundry field | Purpose | A3 dashboard needs it | Status | Notes |
|---|---|---|---|---|---|
| `run_id` | `run.id` | One submitted test run | Yes | verified | Seen in `fixtures/a3/p3/releasefoundry_field_sample.redacted.json`. |
| `dataset_id` | `run.dataset` or `dataset.id` | Dataset/eval grouping | Yes | verified | Seen in `list_runs` and `list_datasets`. |
| `runner_id` | `run.runner` | Person/process that ran it | Nice | verified | Seen in `list_runs`. |
| `run_status` / `status` | `run.result.status` | Run execution status | Yes | verified | Confirmed values include `completed` and `failed`; A3 maps completed/no failures to `passed`. |
| `total_cases` | `run.result.aggregate_metrics.total_tests`, `run.result.aggregate_metrics.total_cases`, or `run.result.total_cases` | Total tests/cases | Yes | verified | Both historical `tests[]` and current `cases[]` shapes expose totals. |
| `passed` | `run.result.aggregate_metrics.tests_passed`, `run.result.aggregate_metrics.passed`, or `run.result.passed` | Passed count | Yes | verified | Confirmed in successful and failed run samples. |
| `failed` | `run.result.aggregate_metrics.tests_failed`, `run.result.aggregate_metrics.failed`, or `run.result.failed` | Failed count | Yes | verified | Confirmed with a real failed run sample. |
| `trace_completeness` | derived from `tests[].action_results` | Evidence coverage | Yes | derived | Real sample exposes actions, not this exact metric. |
| `cases[]` | `run.result.tests[]` | Per-case display rows | Yes | verified | Seen in `list_runs`. |
| `case_id` | `test.test_id` | Single test/case identity | Yes | verified | Seen in `list_runs`. |
| `scenario_id` | `test.test_id` or dataset scenario key | Scenario identity | Yes | derived | Dataset sample has `dataset_source.runs`; run sample has `test_id`. |
| `title` | dataset scenario `title` or `test.test_id` | Human label | Yes | verified | A3 now optionally joins dataset `dataset_source.runs.*.title` into mapped cases, with test/case ID fallback. |
| `started_at` | `test.started_at` or `run.result.started_at` | Timing | Nice | verified | Seen at run and test levels. |
| `ended_at` | `test.completed_at` or `run.result.completed_at` | Timing | Nice | verified | Seen at run and test levels. |
| `latency_ms` | derived from timestamps | Duration | Nice | derived | Real sample uses timestamps. |
| `observations[]` | `action_results[]` | Timeline fallback | Yes | derived | Mapper turns each action result into an A1-like observation. |
| `trace_events[]` | derived from `action_results[]` | Timeline primary display | Yes | derived | Mapper turns action results into A1-like trace events. |
| `tool_calls[]` | `action_results[].tool_calls[]` | Actual tool use | Yes | verified | Seen in `list_runs`. |
| `expected.tool_calls` | `tool_calls[].expected` | Expected tool use | Yes | verified | Seen in `list_runs`. |
| `actual.tool_calls` | `tool_calls[].actual` | Actual tool use | Yes | verified | Seen in `list_runs`. |
| `expected.final_response_points` | `action_results[].expected_response` | Expected response | Yes | verified | Seen in `list_runs`. |
| `actual.final_response` | `action_results[].actual_response` | Agent answer | Yes | verified | Seen in `list_runs`. |
| `score` | `case.grade.score`, `case.score`, or `action_results[].semantic_similarity` | Score | Yes | verified/derived | A3 now prefers explicit ReleaseFoundry case grade score, falls back to case score, and uses semantic similarity only as a provisional action-results score. |
| `score_source` | derived from chosen score field | Score provenance | Yes | derived | Exported as `releasefoundry_case_grade_score`, `releasefoundry_case_score`, `semantic_similarity_average`, or `pass_fail_default`. |
| `passed` per case | `case.grade.passed` or derived from `match_status` and test status | Pass/fail | Yes | verified/derived | Current failed `result.cases[]` sample exposes `case.grade.passed=false`; older `tests[]` samples use derived action status. |
| `primary_failure_class` | no native field observed; derived from `case.grade.metrics`, `match_status`, `argument_comparison`, and divergence fields | Failure cluster | Yes | derived | A real failed run was checked; no named `failure_class` field was present in that sample. |
| `failure_summary` | `divergence_notes` or generated summary from mismatch | Triage text | Yes | verified/derived | Sample field exists; mapper falls back when null. |
| `severity` | backend severity or derived class severity | Cluster severity | Nice | unknown | Need real graded sample. |
| `judge_results[]` | A3 synthetic wrapper around ReleaseFoundry action checks | Drilldown | Nice | derived | Mapper emits `p3_releasefoundry_action_results_judge` for dashboard compatibility. |
| `media_evidence.primary_media_type` | `case.metadata.action_type` or `action_results[].action_type` | Case-level media type | Yes | verified | Seen as `audio` in `fixtures/a3/p3/releasefoundry_run_detail_sample.redacted.json`. |
| `media_evidence.media_types[]` | `audio` / `file` / `image` / `video` action types | Media filtering and evidence badges | Yes | verified | Dataset sample includes `audio` and `file`; request config also mentions image/video generation flags. |
| `media_evidence.action_tags` | `actions[].action_tags` or `case.metadata.action_tags` | Structured media metadata | Yes | verified | File action tags include file metadata such as format/style fields. |
| `media_evidence.output_paths[]` | `actions[].output_path` | Linkable/generated media artifact path | Yes | verified | Present for file action in dataset sample; absent for sanitized audio case sample. |
| `media_evidence.signed_url` | `actions[].signed_url` | Direct signed media/file URL | Optional | partially verified | Field name confirmed for file-like dataset actions; audio/image/video signed URL samples are not yet confirmed. |
| `media_evidence.audio_tags` | `dataset_source.runs.*.audio_tags` or `case.metadata.audio_tags` | Audio profile evidence | Yes | verified | Seen with tone/accent/background-noise-like fields after redaction. |
| `media_evidence.intent_tags` | `dataset_source.runs.*.intent_tags` or `case.metadata.intent_tags` | Scenario intent grouping | Nice | verified | Seen in dataset and run detail samples. |
| `vm_stream` | `case.observations[].vm_stream` | Replay/browser evidence | Yes | verified | Run detail sample includes provider, session id, duration, logs, and synthetic metadata. |
| `trace_events[].event_type` for media | derived as `media.<type>` or `media.vm_stream` | Timeline evidence display | Yes | derived | A3 mapper emits media timeline events from real case observations. |

## Smoke sample findings

- `init()` succeeded and returned redacted user/tenant shape plus feature flags.
- `health_check()` succeeded.
- `list_agents()` succeeded but returned an empty list for this account.
- `list_datasets()` succeeded and showed `dataset_source.dataset_type == "multi_run_storyboard"`.
- `list_datasets()` showed scenario-like entries under `dataset_source.runs.*.actions[]`.
- `list_runs()` succeeded and showed `runs[].result.aggregate_metrics`.
- `list_runs()` showed `runs[].result.tests[].action_results[]`.
- `list_runs()` confirmed expected vs actual text and tool call fields.
- `list_requests()` succeeded and showed generation request shape.
- `list_observability_traces()` failed because this account's `init().features.observability` is `false`.
- Follow-up media calibration saw `audio`, `file`, `action_tags`, `output_path`, and `vm_stream` in sanitized dataset/run detail samples.
- Real run detail can also use an A1-like `run.result.cases[]` shape instead of `run.result.tests[]`; A3 mapper now supports both.
- A 2026-07-06 read-only failed-run probe confirmed:
  - `run.result.status == "failed"`
  - aggregate failed/passed counts
  - `run.result.cases[].status == "failed"`
  - `run.result.cases[].grade.label`
  - `run.result.cases[].grade.passed`
  - `run.result.cases[].grade.score`
  - `run.result.cases[].grade.reason`
  - `run.result.cases[].grade.metrics`
- The same failed-run probe did not expose a named backend `failure_class`; A3 derived `bad_final_response` and `missing_required_tool` from grade metrics and expected/actual evidence.
- A failed request detail confirmed `request.request_status == "failed"` and a failure object under `request.request._failure`; A3 treats this as request provenance, not as case-level grading.
- The official A3 refund demo added stronger end-to-end evidence:
  - dataset id `884`
  - hosted run id `11925`
  - `run.result.cases[]` with 5 cases
  - aggregate 2 pass / 3 fail
  - `cases[].expected`
  - `cases[].grade.actual`
  - `cases[].grade.score`
  - `cases[].grade.passed`
  - `cases[].grade.reason`
  - expected/actual tool calls
  - observations and VM-stream-like trace evidence
  - dataset-derived media channels for audio, file, and image cases
- The 2026-07-07 official-UI-compatible run added the strongest Results-shape evidence so far:
  - hosted run id `11926`
  - `run.result.tests[]` with 5 tests
  - `tests[].action_results[]`
  - aggregate 2 pass / 3 fail
  - expected vs actual response fields
  - expected vs actual tool-call comparison fields
  - dataset-derived media channels for audio, file, and image cases
  - `list_runs(dataset_id=884, summary_only=true)` includes `11926`
  - no `vm_stream` field in this official `tests[]` result, so A3 reports 0 VM stream cases for this source
- `services/report/p3_releasefoundry_mapper.mjs` now supports official wrappers shaped like `response.dataset` and joins `dataset_source.runs` metadata into the mapped cases.

## 2026-07-05 frontend/API continuation

- New read-only API calibration saved:
  - `fixtures/a3/p3/releasefoundry_frontend_api_objects.redacted.json`
  - `fixtures/a3/p3/releasefoundry_run_trace_sample.redacted.json`
  - `fixtures/a3/p3/releasefoundry_media_url_sample.redacted.json`
- `init`, `health_check`, `list_agents`, `list_datasets`, `get_dataset`, `list_runs`, `get_run`, `list_requests`, `get_request`, and signed-url dataset probes succeeded.
- `list_observability_traces` still failed because observability is not enabled for this account.
- `get_run` returned a direct run object whose `result` uses `cases[]`; the redacted run trace sample now records field presence for expected/actual, score, pass/fail, failure-like fields, and tool calls.
- A dataset action field named `signed_url` was confirmed and redacted to `[REDACTED_URL]`.
- A signed-media coverage audit saved `fixtures/a3/p3/releasefoundry_signed_media_url_coverage.redacted.json`; it found 2 redacted `signed_url` keys, both nearest to `file` actions.
- Direct authenticated frontend content extraction from the user's Edge/normal Chrome windows was blocked by the browser-control safety layer, so the first version of the frontend page docs marked UI labels as API/prior-observation-backed unless directly confirmed.

## 2026-07-06 authenticated frontend confirmation

- The user logged into an isolated Chrome profile launched with local CDP debugging.
- Direct read-only UI observation confirmed top-level Lab pages:
  - Datasets: `?tab=analysis`
  - Agents: `?tab=agents`
  - Folders: `?tab=folders`
  - Analytics: `?tab=analytics`
  - Usage: `?tab=usage`
  - Trust: `?tab=trust`
  - API Keys: `?tab=api-keys`
  - Team: `?tab=team`
- Datasets page confirmed search, filter, sort, group, pinned-only, and `New dataset` controls.
- New Dataset confirmed an 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.
- Analytics confirmed product-level fields that A3 can derive locally: agents, datasets, graded runs, overall pass rate, run volume, pass-rate trend, runs by agent, and pass rate by agent.
- Usage confirmed UI quota labels: Images, Audio, Files.
- Trust confirmed a report-like public certificate concept with frozen metrics.
- API Keys and Team were confirmed as admin pages, but they remain outside A3's MVP scope.

The observed account had no UI-visible datasets/runs, so API samples remain the source of truth for populated run detail, case detail, expected-vs-actual, tool calls, score/pass-fail, failure-like fields, trace/timeline, and signed media fields.

## Object mapping by product concept

| Product concept | Local clone term | Real ReleaseFoundry probable term | A3 action |
|---|---|---|---|
| Agent | `runner_id` / local agent class | `Agent` with `id`, `name`, `config` | Show as metadata if returned. |
| Evaluation | Dataset plus run batch | `Dataset` / generated dataset / run list | Use dataset as evaluation group for now. |
| Scenario | `scenario_id` and A2 scenario rows | `dataset_source.runs[]` or `Scenario` | Map titles/actions when dataset sample exists. |
| Run | `RunResult` | `Run` with nested `result` | Map into A3 `runs[]`. |
| Trace | `trace_events[]` / `observations[]` | Observability `Trace` or run `action_results[]` | Normalize to A1-style timeline. |
| Tool call | `ToolCall` with `name`, `arguments`, `output` | `tool_calls[].expected` / `actual` | Preserve expected/actual pair. |
| Expected vs actual | `case.expected` / `case.actual` | `action_results[]` comparisons | Flatten into panels. |
| Pass/fail | A1/A2 `passed` | Aggregate and per-test grading fields | Use real field if present; otherwise derive. |
| Failure class | A2 `primary_failure_class` | backend failure classification | Keep raw and normalized forms. |
| Report | A3 export JSON/CSV/Markdown | Dashboard/report data | Feed through existing report builder. |

## Minimum A3 mapper output

The mapper should emit:

```json
{
  "runFixture": {
    "schema_version": "a3.dashboard_fixture.v1",
    "fixture_id": "p3_releasefoundry_calibrated_sample",
    "runs": []
  },
  "gradeFixture": {
    "schema_version": "a3.grade_fixture.v1",
    "fixture_id": "p3_releasefoundry_calibrated_grades",
    "grade_results": []
  }
}
```

## Remaining unknowns

- Whether other ReleaseFoundry accounts or newer runs expose a native backend failure class separate from `case.grade.metrics`, `match_status`, and local/A2-derived classes.
- Current failed-run and official demo evidence include grade labels, pass/fail, score, reason, and metrics, but not a named `failure_class`.
- Does the dashboard API expose eval/evaluation objects separately from datasets?
- Are production observability traces linkable to testing runs when the feature is enabled?
- What the official populated Results/run-detail frontend looks like after a fresh login and whether it shows run `11926` with the same fields.
- Score-source policy is now decided: A3 prefers explicit ReleaseFoundry grade fields and records `score_source`; `semantic_similarity` is only a provisional fallback for action-results samples without a stronger score.
- Signed media URL field name is confirmed as `actions[].signed_url` for file-like dataset actions, but audio/image/video signed URL behavior and permission-safe rendering rules are still unknown.
