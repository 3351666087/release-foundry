# P3 Field Mapping

Status legend:

- `verified`: confirmed by local API smoke sample or direct SDK model.
- `probable`: present in SDK docs/artifact but not yet seen in this account data.
- `derived`: not a native platform field in the sample; A3 calculates it from verified fields.
- `unknown`: not enough evidence yet.

## Summary mapping

| Local A3 field | Real Ashr field | Purpose | A3 dashboard needs it | Status | Notes |
|---|---|---|---|---|---|
| `run_id` | `run.id` | One submitted test run | Yes | verified | Seen in `fixtures/a3/p3/ashr_field_sample.redacted.json`. |
| `dataset_id` | `run.dataset` or `dataset.id` | Dataset/eval grouping | Yes | verified | Seen in `list_runs` and `list_datasets`. |
| `runner_id` | `run.runner` | Person/process that ran it | Nice | verified | Seen in `list_runs`. |
| `run_status` / `status` | `run.result.status` | Run execution status | Yes | verified | Sample value shape: `completed`. A3 maps completed/no failures to `passed`. |
| `total_cases` | `run.result.aggregate_metrics.total_tests` | Total tests/cases | Yes | verified | Seen in `aggregate_metrics`. |
| `passed` | `run.result.aggregate_metrics.tests_passed` | Passed count | Yes | verified | Seen in `aggregate_metrics`. |
| `failed` | `run.result.aggregate_metrics.tests_failed` | Failed count | Yes | verified | Seen in `aggregate_metrics`. |
| `trace_completeness` | derived from `tests[].action_results` | Evidence coverage | Yes | derived | Real sample exposes actions, not this exact metric. |
| `cases[]` | `run.result.tests[]` | Per-case display rows | Yes | verified | Seen in `list_runs`. |
| `case_id` | `test.test_id` | Single test/case identity | Yes | verified | Seen in `list_runs`. |
| `scenario_id` | `test.test_id` or dataset scenario key | Scenario identity | Yes | derived | Dataset sample has `dataset_source.runs`; run sample has `test_id`. |
| `title` | dataset scenario `title` or `test.test_id` | Human label | Yes | verified | Dataset sample has `dataset_source.runs.*.title`; run sample needs join or fallback. |
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
| `score` | `action_results[].semantic_similarity` and `aggregate_metrics.average_similarity_score` | Score | Yes | verified/derived | Platform exposes similarity; A3 normalizes 0-1 to 0-100. |
| `passed` per case | derived from `match_status` and test status | Pass/fail | Yes | derived | Real sample has `match_status`; no separate per-case `passed` field was seen. |
| `primary_failure_class` | derived from `match_status`, `argument_comparison`, and divergence fields | Failure cluster | Yes | derived | No native backend failure-class field seen in this sample. |
| `failure_summary` | `divergence_notes` or generated summary from mismatch | Triage text | Yes | verified/derived | Sample field exists; mapper falls back when null. |
| `severity` | backend severity or derived class severity | Cluster severity | Nice | unknown | Need real graded sample. |
| `judge_results[]` | A3 synthetic wrapper around Ashr action checks | Drilldown | Nice | derived | Mapper emits `p3_ashr_action_results_judge` for dashboard compatibility. |
| `media_evidence.primary_media_type` | `case.metadata.action_type` or `action_results[].action_type` | Case-level media type | Yes | verified | Seen as `audio` in `fixtures/a3/p3/ashr_run_detail_sample.redacted.json`. |
| `media_evidence.media_types[]` | `audio` / `file` / `image` / `video` action types | Media filtering and evidence badges | Yes | verified | Dataset sample includes `audio` and `file`; request config also mentions image/video generation flags. |
| `media_evidence.action_tags` | `actions[].action_tags` or `case.metadata.action_tags` | Structured media metadata | Yes | verified | File action tags include file metadata such as format/style fields. |
| `media_evidence.output_paths[]` | `actions[].output_path` | Linkable/generated media artifact path | Yes | verified | Present for file action in dataset sample; absent for sanitized audio case sample. |
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

## Object mapping by product concept

| Product concept | Local clone term | Real Ashr probable term | A3 action |
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
    "fixture_id": "p3_ashr_calibrated_sample",
    "runs": []
  },
  "gradeFixture": {
    "schema_version": "a3.grade_fixture.v1",
    "fixture_id": "p3_ashr_calibrated_grades",
    "grade_results": []
  }
}
```

## Remaining unknowns

- Where, if anywhere, does real Ashr expose a native backend failure class separate from `match_status` and `llm_judgment`?
- Does a failing real run include richer backend grading details than the successful sample?
- Does the dashboard API expose eval/evaluation objects separately from datasets?
- Are production observability traces linkable to testing runs when the feature is enabled?
- Should A3 keep `semantic_similarity` as the score, or wait for a server-side grade field when available?
- Direct signed media URLs for audio/image/video were not available in the sanitized sample; A3 records this as `known_gaps`.
