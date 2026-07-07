# A3 Raw A1/A2 Dashboard Sources - 2026-07-07

## Scope

This closes the previous gap where `report_builder.mjs` could consume raw A1/A2 data, but the dashboard did not expose those raw sources in the Data selector.

## What Changed

Added two dashboard data sources:

- `Raw A1 RunResult`
  - Loads `docs/a1/evidence/local_run_30.json`.
  - Uses A3 normalization to show 30 raw A1 cases directly.
- `Raw A2 Single Case`
  - Loads `fixtures/a2/runs/a2_s004_missing_tool.json`.
  - Loads `fixtures/a2/results/a2_s004_missing_tool_grade.json`.
  - Uses A3 normalization to show the A2 missing-tool case directly.

## Why It Matters

Before this change, A3 could prove raw A1/A2 compatibility in tests, but the UI still only exposed A3 mock and P3 mapped samples.

After this change, reviewers can open the dashboard and switch between:

- A3 mock fixture
- Raw A1 RunResult
- Raw A2 single-case fixture
- P3 media sample
- P3 official demo run

This makes the A1/A2/A3 contract more visible and easier to verify during group review.

## Browser Evidence

Local smoke URL:

```text
http://127.0.0.1:4173/apps/dashboard/index.html?source=raw-a2
```

Observed:

- Raw A1 source loaded 1 run, 30 cases, 100% pass rate.
- Raw A2 source loaded 1 run, 1 case, 0% pass rate.
- Export Safety stayed `passed`.
- Browser error log was empty.

Screenshot:

- `docs/screenshots/a3-dashboard-raw-a2-source.png`

## Tests

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
56 tests
56 pass
0 fail
```
