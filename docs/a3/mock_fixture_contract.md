# A3 Mock Fixture Contract

## Purpose

This contract lets A3 build dashboard UI from local fixture data without calling the real ReleaseFoundry API.

The original A3 mock data was hand-maintained while A1/A2 were still draft PRs. After A1/A2 merged, the mock fixtures were replaced with generated fixtures built from the merged A2 scenario pack, executable run fixtures, and aggregate grade results.

Regenerate them with:

```text
node services/report/a3_fixture_builder.mjs --write
```

The generator is covered by `tests/a3/a3_fixture_builder.test.mjs`, which verifies that the checked-in A3 mock fixtures match the current merged A2 outputs.

## `fixtures/a3/mock_run_results.json`

Top-level fields:

- `schema_version`: `a3.dashboard_fixture.v1`
- `fixture_id`: fixture name
- `source_notes`: source path provenance
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

A3 no longer keeps hand-maintained mock data as the source of truth. The current replacement path is:

1. Read `packages/scenarios/a2_g3_full_pack.json`.
2. Read `fixtures/a2/results/a2_g3_grade_results.json`.
3. Read all `fixtures/a2/runs/*.json`.
4. Use `services/report/a3_fixture_builder.mjs` to write the A3 view model into `fixtures/a3/mock_run_results.json` and `fixtures/a3/mock_grade_results.json`.

This keeps the dashboard stable while making the mock data reproducible from merged A2 outputs.
