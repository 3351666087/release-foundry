# P3 Regression Factory Growth - 2026-07-07

## Goal

Convert failed replay cases into regression-test candidates that can be attached to a release gate.

This moves A3 from "we can see the failure" to "we can turn the failure into a repeatable test before the next release."

## Added Capability

- Added `summarizeRegressionFactory()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `regression_factory`
- Added Markdown report section:
  - `Regression Factory`
- Added dashboard panel:
  - `Regression Factory`
- Added print/PDF report section:
  - `Regression Factory`
- Added dashboard and report tests.

## What It Shows

The Regression Factory summarizes:

- candidate count
- ready candidates
- blocked candidates
- candidates needing evidence
- coverage gaps
- tool-call regression candidates
- media regression candidates
- official Results review parity
- generated suite plan
- per-candidate required contracts
- proposed regression assertions
- next action before promotion

## A1/A2/Official Calibration

- A1 provides run id, case id, scenario id, trace events, observations, expected vs actual, tool calls, media metadata, and replay evidence.
- A2 provides pass/fail, score, primary failure class, judge evidence, severity, remediation, and coverage.
- Official frontend code-crawl evidence provides Results review parity signals without copying official source code.

## Commercial Meaning

This is a revenue-facing capability because it answers a buyer's post-incident question:

> "After this agent failure is fixed, how do we prove it will not happen again before the next release?"

Regression Factory turns incident replay into a regression suite plan that can be bound to:

- PR gate
- release gate
- reviewer workflow
- audit bundle
- self-host evidence review

## Safety

- No live API call was required for this pass.
- No `.env.local`, API key, token, cookie, email, or raw signed media URL was read or committed.
- Media regression candidates remain metadata-only.
- Official frontend source code was not copied.
- A1 runner logic and A2 judge semantics were not changed.

## Verification

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

## Next Growth Points

1. Emit an actual generated regression fixture file from each ready candidate.
2. Bind generated regression candidates to the A3 Gate CLI output.
3. Add a PR comment section listing newly generated regressions.
4. Add a page-state fixture for `visual_results_pending` vs `summary_api_visible`.
5. Add redaction regression tests for every export format.
