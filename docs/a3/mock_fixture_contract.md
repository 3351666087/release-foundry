# A3 Mock Fixture Contract

## Purpose

This contract lets A3 build dashboard UI before A1/A2 draft PRs are merged. It is intentionally small and local-only.

## `fixtures/a3/mock_run_results.json`

Top-level fields:

- `schema_version`: `a3.dashboard_fixture.v1`
- `fixture_id`: fixture name
- `source_notes`: PR and path provenance
- `runs[]`: list of local run summaries

Run fields:

- `run_id`
- `dataset_id`
- `runner_id`
- `status`
- `total_cases`
- `passed`
- `failed`
- `errored`
- `timed_out`
- `started_at`
- `ended_at`
- `duration_ms`
- `trace_completeness`
- `cases[]`

Case fields:

- `case_id`
- `scenario_id`
- `title`
- `family`
- `status`
- `score`
- `latency_ms`
- `primary_failure_class`
- `severity`
- `failure_summary`
- `expected`
- `actual`
- `observations[]`
- `trace_events[]`

## `fixtures/a3/mock_grade_results.json`

Top-level fields:

- `schema_version`: `a3.grade_fixture.v1`
- `fixture_id`
- `source_notes`
- `grade_results[]`

Grade fields:

- `scenario_id`
- `case_id`
- `passed`
- `score`
- `primary_failure_class`
- `judge_results[]`

Judge fields:

- `judge_mode`
- `passed`
- `score`
- `max_score`
- `failure_analysis`
- `evidence`

## Mapping into dashboard

- Run summary cards use `runs[]` aggregates and normalized case scores.
- Run List uses normalized case rows.
- Expected vs Actual uses `case.expected` and `case.actual`.
- Trace Timeline uses `case.trace_events`; if missing, it falls back to `case.observations`.
- Failure Cluster uses `grade.primary_failure_class` first, then `case.primary_failure_class`.
- Report Export uses the same normalized data as the UI.

## Replacement rule

After A1/A2 merge, A3 should not keep hand-maintained mock data as the source of truth. It should either:

1. Read A1/A2 fixture JSON directly, or
2. Add a small transform that writes the same A3 view model from real A1/A2 outputs.
