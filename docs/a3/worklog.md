# A3 Worklog

## 2026-07-04 - First A3 pass

### Goal

Start A3 Dashboard & Triage work after A1/A2 opened draft PRs. Do not merge A1/A2. Read their contracts and create an independent dashboard skeleton that can consume A1/A2-style fixtures.

### Commands

```text
gh repo clone 3351666087/ashr-codex-factory ashr-codex-factory
git fetch origin
git status -sb
gh pr list --repo 3351666087/ashr-codex-factory --state open --json number,title,headRefName,baseRefName,isDraft,author,updatedAt,url
git diff --name-status origin/main...origin/codex/a1-local-sdk-runner
git diff --name-status origin/main...origin/dev/a2-scenario-judge
gh pr view 1 --repo 3351666087/ashr-codex-factory --json title,body,files,commits,reviews,comments
gh pr view 2 --repo 3351666087/ashr-codex-factory --json title,body,files,commits,reviews,comments
git switch -c codex/a3-dashboard-triage
node --test tests/a3/report_builder.test.mjs
python -m http.server 5173 --bind 127.0.0.1
```

### PR reconnaissance

- PR #1: `A1 local SDK runner trace loop`, draft, branch `codex/a1-local-sdk-runner`.
- PR #2: `A2: Scenario and judge foundation`, draft, branch `dev/a2-scenario-judge`.
- Main branch has only `README.md`, so A3 cannot directly import merged A1/A2 files yet.

### Implemented

- Added A3 mock run fixture based on A1/A2 field names.
- Added A3 mock grade fixture based on A2 grade output.
- Added pure report builder functions in `services/report/report_builder.mjs`.
- Added static dashboard skeleton in `apps/dashboard/index.html`.
- Added A3 tests for summary, clustering, and exports.
- Added A3 integration plan, mock fixture contract, and acceptance checklist.
- Verified the dashboard in browser at `http://127.0.0.1:5173/apps/dashboard/index.html`.
- Captured desktop, failed case, failure cluster, and mobile viewport screenshots.
- Added 6 dashboard filters: status, scenario family, failure class, run, severity, and score band.
- Added selected-case judge drilldown below Expected vs Actual.
- Added report-builder filter helpers so filtering can be tested outside the UI.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

Browser checks:

- Summary rendered `Runs=1`, `Cases=4`, `Pass Rate=50%`, `Trace Complete=100%`.
- Failure clusters rendered `missing_required_tool` and `wrong_arguments`.
- Failed case detail for `A2-S004` showed expected `web.search` and actual empty `tool_calls`.
- Mobile viewport rendered single-column layout at width 390.
- Filter logic covers failed + major + 70-89 score band.
- Captured 10 demo screenshots covering summary, failed detail, clusters, filters, wrong argument detail, judge drilldown, export actions, and mobile viewport.

### Evidence paths

- `docs/a3/a3_integration_plan.md`
- `docs/a3/mock_fixture_contract.md`
- `docs/a3/acceptance_checklist.md`
- `fixtures/a3/mock_run_results.json`
- `fixtures/a3/mock_grade_results.json`
- `apps/dashboard/index.html`
- `services/report/report_builder.mjs`
- `tests/a3/report_builder.test.mjs`
- `docs/screenshots/a3-dashboard-summary.png`
- `docs/screenshots/a3-dashboard-case-detail.png`
- `docs/screenshots/a3-dashboard-failure-clusters.png`
- `docs/screenshots/a3-dashboard-mobile-viewport.png`
- `docs/screenshots/a3-01-summary.png`
- `docs/screenshots/a3-02-failed-case-detail.png`
- `docs/screenshots/a3-03-failure-clusters.png`
- `docs/screenshots/a3-04-filter-failed.png`
- `docs/screenshots/a3-05-filter-major.png`
- `docs/screenshots/a3-06-filter-score-band.png`
- `docs/screenshots/a3-07-wrong-argument-detail.png`
- `docs/screenshots/a3-08-judge-drilldown.png`
- `docs/screenshots/a3-09-export-actions.png`
- `docs/screenshots/a3-10-mobile-viewport.png`

### Known gaps

- A1/A2 draft PR files are not merged into main, so A3 uses mock fixtures for now.
- Root package/test configuration does not exist yet; A3 tests use Node's built-in test runner directly.

### Next top 3

1. Add judge-mode filter after A2 has more varied sample judge modes.
2. Create a transform script after A1/A2 PRs merge so A3 can replace mock fixtures with real outputs.
3. Replace the static HTML shell with the team's final frontend stack if the repo standardizes on one.

## 2026-07-04 - P3 Ashr calibration

### Goal

Start P3/G3 real Ashr calibration after A1, A2, and A3 merged into main. Keep the work small and safe: verify key hygiene, inspect real Ashr field shapes, save redacted evidence, and add only a narrow mapper for A3.

### Implemented

- Added `docs/a3/p3_ashr_calibration_plan.md`.
- Added `docs/a3/p3_field_mapping.md`.
- Added `docs/a3/p3_worklog.md`.
- Saved redacted Ashr smoke fixtures under `fixtures/a3/p3`.
- Added `services/report/p3_ashr_mapper.mjs`.
- Added `tests/a3/p3_ashr_mapper.test.mjs`.
- Updated `docs/a3/acceptance_checklist.md`.

### Smoke test summary

- `.env.local` exists and is ignored by Git.
- The key was read only through environment variables and was not printed.
- `init()`, `health_check()`, `list_datasets()`, `list_runs()`, and `list_requests()` succeeded.
- `list_agents()` succeeded but returned an empty list.
- `list_observability_traces()` failed because this account has `features.observability == false`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 8
pass 8
fail 0
```

### Next top 3

1. Verify native backend failure-class fields with a real failing Ashr run.
2. Decide whether A3 should display `semantic_similarity` as the score or wait for a stronger server grade field.
3. Join `list_runs()` with `list_datasets()` so A3 cases can use real scenario titles.
