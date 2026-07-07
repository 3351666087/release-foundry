# A3 Dashboard Webapp Migration And A1/A2 Compatibility - 2026-07-07

## Scope

This round keeps A3 inside owned paths and does not change A1 runner logic or A2 judge semantics.

Changed areas:

- `apps/dashboard`
- `services/report`
- `tests/a3`
- `docs/a3`

## What Changed

### Dashboard split

The dashboard was migrated from one oversized HTML file into a small webapp shell:

- `apps/dashboard/index.html`
  - HTML structure only.
  - Loads `./src/styles.css`.
  - Loads `./src/app.mjs`.
- `apps/dashboard/src/styles.css`
  - Former inline CSS.
- `apps/dashboard/src/app.mjs`
  - Former inline module script.

Before this round, `index.html` was more than 3,000 lines. After the split, `index.html` is about 400 lines, and the behavior lives in a dedicated module.

Why this matters:

- A3 features are now easier for teammates to edit.
- UI work and report logic are less tangled.
- Future migration to React/Vite remains possible, but this round avoids adding new dependencies.

### A1/A2 compatibility

`services/report/report_builder.mjs` now normalizes more raw A1/A2 shapes before dashboard/report logic runs.

Supported inputs now include:

- A3 aggregate run fixtures: `{ runs: [{ cases: [...] }] }`
- A1 RunResult root object: `{ run_id, cases, trace_completeness, ... }`
- A1 loose case lists: `{ cases: [...] }`
- A1 `ashr.clone.run.v1` run fixture shape with `run`, `events`, `expected`, and `replay`
- A2 single run fixture: `{ scenario_id, case_id, run, expected }`
- A2 aggregate grade report: `{ grade_results: [...] }`
- A2 single local judge result: `{ case_id, passed, score, primary_failure_class, judge_results }`

The normalizer now fills A3-friendly fields:

- `run_id`
- `dataset_id`
- `runner_id`
- `expected`
- `actual`
- `trace_events`
- `observations`
- `trace_ready`
- `media_evidence`
- `score`
- `passed`
- `primary_failure_class`
- `judge_results`
- `judge_modes`

This makes A3 less dependent on pre-converted mock fixtures.

### Export Redaction Firewall

This round also keeps the newly added export safety work:

- Added `services/report/export_redaction_firewall.mjs`.
- JSON reports now include `export_redaction_firewall`.
- Markdown reports include `Export Redaction Firewall`.
- CSV cells are scrubbed and hardened against spreadsheet formula injection.
- Gate CLI redaction now reuses the shared firewall instead of having a private copy.
- Dashboard now has an `Export Safety` panel.

## A1/A2 Calibration

A1 signals used by A3:

- run/case ids
- expected vs actual
- trace events
- observations
- agent output
- tool calls
- optional media / VM stream evidence

A2 signals used by A3:

- pass/fail
- score
- primary failure class
- judge results
- failure analysis
- severity
- remediation

## Verification

Focused tests:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
55 tests
55 pass
0 fail
```

New compatibility tests prove:

- A3 can consume `docs/a1/evidence/local_run_30.json` directly.
- A3 can consume `fixtures/a2/runs/a2_s004_missing_tool.json` plus `fixtures/a2/results/a2_s004_missing_tool_grade.json` directly.

## Remaining Follow-Ups

- Add a dedicated dashboard data-source selector for raw A1/A2 fixtures, not only A3 mock and P3 samples.
- Consider a future React/Vite migration if the team wants component-level UI ownership.
- Add CI scanning for export firewall rules across generated docs, fixtures, and dashboard downloads.
