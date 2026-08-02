# A3 Integration Plan

## Role

A3 owns Dashboard & Triage. The goal is to turn A1 run/trace output and A2 judge output into visible product evidence: run status, case detail, expected vs actual, trace timeline, failure clusters, and exportable reports.

## PR reconnaissance

Current base branch `main` only contains the project README. A1 and A2 are still draft PRs:

- PR #1 `A1 local SDK runner trace loop`, branch `origin/agent/a1-local-sdk-runner`
- PR #2 `A2: Scenario and judge foundation`, branch `origin/dev/a2-scenario-judge`

A3 should not merge or modify those branches. This first A3 pass reads their contracts and creates a local A3 skeleton that can later swap mock fixtures for merged real outputs.

## A1 data A3 can consume

From PR #1:

- `docs/a1/evidence/local_run_30.json`
- `examples/agents/fixtures/tool_math_success.json`
- `docs/a1/schemas/run_result.schema.json`
- `docs/a1/schemas/case_result.schema.json`
- `docs/a1/schemas/trace_event.schema.json`

Useful fields:

| Field | Meaning | Dashboard use |
|---|---|---|
| `run_id` | One eval execution ID | Run selector, report identity |
| `dataset_id` | Dataset or scenario pack | Run metadata |
| `runner_id` | Local runner identity | Run metadata |
| `status` | Run or case status | Pass/fail badges |
| `total_cases`, `passed`, `failed`, `errored`, `timed_out` | Aggregate counts | Summary cards |
| `trace_completeness` | Share of cases with trace evidence | Evidence quality card |
| `cases[]` | Per-case run output | Run list and case detail |
| `case_id`, `scenario_id`, `title` | Case identity | List row and detail title |
| `observations[]` | Dialogue/tool observations | Timeline fallback |
| `trace_events[]` | Normalized trace events when present | Timeline primary source |
| `agent_output.text` | Final response | Actual panel |
| `agent_output.tool_calls[]` | Actual tool calls | Actual panel and trace |
| `expected` | Expected text/tool calls | Expected panel |

## A2 data A3 can consume

From PR #2:

- `docs/a2/a1_a3_handoff.md`
- `docs/a2/failure_taxonomy_v0.md`
- `packages/scenarios/a2_g2_seed_pack.json`
- `fixtures/a2/results/a2_s001_pass_grade.json`
- `fixtures/a2/results/a2_s004_missing_tool_grade.json`
- `fixtures/golden/a2_g2_golden_cases.json`

Useful fields:

| Field | Meaning | Dashboard use |
|---|---|---|
| `passed` | Case pass/fail | Status badge and filters |
| `score` | Overall score | List row, detail, export |
| `primary_failure_class` | Main failure category | Failure cluster grouping |
| `judge_results[]` | Per-judge output | Detail drilldown later |
| `failure_analysis.summary` | Human-readable root cause | Case detail and cluster text |
| `failure_analysis.severity` | Severity | Cluster severity |
| `failure_analysis.remediation[]` | Suggested fix | Future triage recommendations |
| `evidence.tool_call_ids` | Tool evidence | Trace link target later |
| `evidence.final_response_excerpt` | Final answer evidence | Detail and export |

## Dashboard views

1. Summary cards: run count, case count, pass rate, average score, trace completeness.
2. Run List: filtered case/run rows with status, scenario, failure class, and score.
3. Case Detail: selected case metadata plus expected vs actual JSON.
4. Trace Timeline: A1 trace events or observations ordered by sequence/turn.
5. Failure Clusters: failed cases grouped by A2 `primary_failure_class`.
6. Report Export: JSON, CSV, and Markdown report output.

## Filters

Initial filters:

- Status: all/passed/failed
- Scenario family
- Failure class
- Run ID
- Severity
- Score band

Next filters after A1/A2 merge:

- Dataset ID
- Judge mode
- Time range

## Mock-to-real data strategy

Current implementation uses:

- `fixtures/a3/mock_run_results.json`
- `fixtures/a3/mock_grade_results.json`

When A1/A2 PRs merge, replace or generate these fixtures from:

- A1 `RunResult` JSON
- A2 `grade_run` output JSON

The dashboard imports pure report functions from `services/report/report_builder.mjs`, so the app and tests share the same normalization logic.

## Current assumptions

- A1 and A2 PRs remain draft and should not be merged by A3.
- A3 may read PR files and create mock fixtures derived from their field names.
- A2 score values can be 0-100; A1 local scores can be 0-1. A3 normalizes both into 0-100 display scores.
- `trace_events` is preferred for timeline display; `observations` is the fallback.

## Current blockers

- Main branch does not yet contain A1/A2 code or fixtures.
- There is no shared root package/test config yet.
- A3 screenshots require running the static app locally after this branch is checked out.
