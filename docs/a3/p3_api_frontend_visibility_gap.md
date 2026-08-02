# P3 API vs Frontend Visibility Gap

## Why this matters

A3 has enough real ReleaseFoundry API evidence to map datasets, runs, requests, cases, expected vs actual, scores, pass/fail, and failure evidence. The remaining frontend gap is different: the authenticated Lab UI currently does not show the same populated objects that the API returns.

This means A3 should keep using sanitized API fixtures for populated run/case/detail evidence until a UI-visible hosted run is available.

## 2026-07-06 read-only comparison

New read-only API probes were saved under `fixtures/a3/p3`:

- `releasefoundry_dataset_probe_after_frontend_empty.redacted.json`
- `releasefoundry_run_probe_after_frontend_empty.redacted.json`
- `releasefoundry_request_probe_after_frontend_empty.redacted.json`
- `releasefoundry_failed_run_dataset_detail.redacted.json`
- `releasefoundry_frontend_session_expired_network.redacted.json`
- `releasefoundry_frontend_relogin_top_level_summary.redacted.json`

API counts from the sanitized probes:

| Object | API count | Evidence |
|---|---:|---|
| Datasets | 3 | `list-datasets` |
| Runs | 2 | `list-runs` |
| Requests | 5 | `list-requests` |

API-confirmed object shapes:

| Object | Confirmed fields |
|---|---|
| Dataset | `id`, `name`, `dataset_type`, `dataset_source`, `request_id`, `run_count`, `created_at` |
| Run | `id`, `dataset`, `result.status`, `result.aggregate_metrics`, `result.cases[]` or `result.tests[]` |
| Request | `id`, `request_name`, `request_status`, `request`, `actual_duration_s`, `estimated_duration_s` |
| Dataset detail | `dataset.dataset_source.dataset_type`, `dataset.dataset_source.runs`, `dataset.dataset_source.total_runs` |

Authenticated frontend state observed in Chrome/CDP:

| Page | Frontend state |
|---|---|
| Datasets / `?tab=analysis` | Loaded, but showed 0 UI-visible datasets and `No datasets match your filters.` |
| Analytics / `?tab=analytics` | Loaded, but showed 0 agents, 0 datasets, 0 graded runs, and not enough data. |
| Trust / `?tab=trust` | Loaded, but showed run-tests-first empty state. |

Fresh relogin note:

- After the user logged in again, read-only Chrome/CDP observation confirmed the Lab frontend session was valid again.
- Top-level Lab page requests and `api.releasefoundry.example/testing-platform-api` POSTs returned `200`, not `401`.
- The visible data state did not change: Datasets still showed 0 visible datasets, Analytics still showed 0 graded runs, and Trust still showed the run-tests-first empty state.

## Interpretation

Current evidence says:

- The ReleaseFoundry API is usable and returns populated objects.
- The Lab frontend is reachable after manual login.
- The current Lab frontend view does not expose the same populated API objects in its visible pages.
- An earlier network probe showed the browser session had expired: the UI displayed sign-in text and frontend POST requests to `api.releasefoundry.example/testing-platform-api` returned `401`.
- A later fresh-login pass restored frontend access, but the UI still did not expose a populated dataset/run.
- Earlier empty-state behavior may still involve filters, workspace visibility rules, object type differences, repo scoping, or product separation between API-generated calibration objects and UI-visible Lab artifacts.
- Deeper page calibration now requires one UI-visible populated hosted run, not just login.

We should not guess the frontend detail routes or build around unconfirmed UI behavior.

## Session-expired network note

The browser session and the local API key are separate credentials:

| Channel | Current evidence | Meaning |
|---|---|---|
| Local API probe via `.env.local` / `RELEASEFOUNDRY_API_KEY` | Still returns datasets/runs/requests in redacted fixtures | Good source for populated A3 calibration data |
| Logged-in Lab frontend session | Fresh relogin pass returned `200`, but still showed empty top-level data | Good source for navigation/empty-state/product logic, not yet for populated run/case detail |

No headers, cookies, tokens, response bodies, account values, or screenshots were saved during the frontend probes.

## A3 MVP decision

A3 should:

- Continue using sanitized API fixtures as the source of truth for populated run/case/detail behavior.
- Keep the dashboard local and read-only.
- Keep failure class derived from confirmed grade/evidence fields.
- Treat frontend pages as product inspiration for navigation, empty states, analytics, usage, and report workflows.

A3 should not:

- Depend on the Lab frontend to supply populated run/case details yet.
- Render live signed media URLs until per-modality access and redaction rules are confirmed.
- Copy account, API-key, team, billing, or trust-publishing flows into the student MVP.

## Next proof needed

## 2026-07-07 update: API summary-visible run

A second run was created for dataset `884` after discovering that the official frontend expects `run.result.tests[].action_results[]` rather than only the local clone's `run.result.cases[]` shape.

New evidence:

| Object | Evidence |
|---|---|
| Official UI-shaped result fixture | `fixtures/a3/p3/releasefoundry_dataset_884_demo_run_result.official_ui_tests.synthetic.json` |
| Real create-run response | `fixtures/a3/p3/releasefoundry_dataset_884_create_run_ui_tests_real.redacted.json` |
| Run detail | `fixtures/a3/p3/releasefoundry_dataset_884_run_11926_ui_tests_detail.redacted.json` |
| Full list-runs check | `fixtures/a3/p3/releasefoundry_dataset_884_list_runs_ui_tests_after_create.redacted.json` |
| Frontend-style summary list-runs check | `fixtures/a3/p3/releasefoundry_dataset_884_list_runs_summary_ui_tests_after_create.redacted.json` |

Confirmed:

- run `11926` exists for dataset `884`
- `get_run(11926)` returns `result.tests[]`
- `list_runs(dataset_id=884)` returns `11926`
- `list_runs(dataset_id=884, summary_only=true)` also returns `11926`
- A3 local dashboard displays run `11926`

Still not confirmed:

- The in-app browser was logged out, so the official visual Results tab could not be checked in this round.

The next useful external evidence is now a visual logged-in Lab check for run `11926`. With that, A3 can verify:

- run detail path
- case detail layout
- expected vs actual frontend labels
- tool-call display
- trace/timeline display
- frontend failure labels
