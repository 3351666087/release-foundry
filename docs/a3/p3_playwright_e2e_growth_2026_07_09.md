# A3 Playwright E2E Growth - 2026-07-09

## Lane

A3 / Product Console / Commercial UI / Report Center / Review Workflow.

## What changed

- Added root Playwright tooling:
  - `package.json`
  - `package-lock.json`
  - `playwright.config.ts`
- Added E2E test files:
  - `tests/e2e/static-dashboard-server.mjs`
  - `tests/e2e/a3-dashboard-commercial.spec.ts`
- The E2E suite serves the real `apps/dashboard/index.html` shell and checks visible product surfaces, not a stub page.
- Hardened the local static server for browser-style asset loading with `clientError`, file-stream error, and response error handling.

## Commercial surfaces covered

- A3 Product Console
- Run metrics and case detail
- Trace Timeline
- Failure Clusters
- Report Center
- Release Evidence
- Reviewer Workflow
- SaaS Admin Console
- Enterprise Readiness
- API/DB/usage/audit contract visibility
- Raw A2 source switching

## API / DB / Event / Artifact Contract

- API: no new API route was added. E2E asserts the dashboard-visible A3 surfaces for `GET /api/a3/dashboard`, A1/A2 import routes, product console, review workflow, report center, admin console, and artifact registry.
- DB: E2E checks the existing dashboard-visible DB contract language, including tenant/project context, `team_members`, `api_keys`, and usage-meter rows. It does not open a DB connection or write data.
- Event: no production event is emitted. The test verifies audit/review/release evidence surfaces and avoids clicking mutation-style admin controls.
- Artifact: successful E2E saves `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`; transient Playwright traces/screenshots stay under ignored `docs/screenshots/playwright-results/`.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: E2E verifies dashboard-visible tenant/project strings on the Product Console (`org-local` / `project-local`).
- Auth/RBAC: E2E verifies SaaS Admin and RBAC Matrix visibility, but does not perform hosted login or mutate identities.
- Usage: E2E verifies Usage meters are visible in the SaaS Runtime panel.
- Audit: E2E verifies Report Center, Release Evidence, Reviewer Workflow, and Enterprise Readiness surfaces are visible.
- Secret safety: no `.env.local`, browser cookies, API keys, or account values are read.

## A1 / A2 Calibration

- A1: E2E checks A1 import API surface text and A1 trace references.
- A2: E2E checks A2 import API surface text, A2 judge evidence, and raw A2 fixture source switching.
- The test does not change A1 runner logic or A2 judge semantics.

## How to run

```text
npm install
npm run test:e2e
```

The same suite can be invoked directly after dependencies are installed:

```text
npx playwright test
```

If browsers are missing:

```text
npm run playwright:install
npm run test:e2e
```

On Windows PowerShell, `npm.ps1` / `npx.ps1` may be blocked by the local execution policy. Use `npm.cmd` / `npx.cmd` in that environment.

## Verification Status

- Initial `npx.cmd playwright test` reached the Playwright runner but failed because Chromium was not installed locally.
- Ran `npx.cmd playwright install chromium`, which installed Chrome for Testing, Chromium headless shell, FFmpeg, and Winldd into the local Playwright browser cache.
- Final verification: `npx.cmd playwright test` passed 4/4 tests in Chromium.
- NPM script verification: `npm.cmd run test:e2e` passed 4/4 tests in Chromium.
- Screenshot evidence: `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`.
- CI should install browsers explicitly before running this lane.

## Failure Points Observed

- PowerShell script execution policy blocks bare `npm` / `npx` shims on this workstation; `.cmd` shims work.
- Fresh Playwright installs need `npx playwright install chromium` before browser-backed tests can run.
- Early assertions were corrected to match the real dashboard text: official-demo case IDs, first-page DB table slice, and `major` triage severity.
- The local static server needed stream/client error handling to avoid intermittent connection refusal during browser runs.

## Next Growth

1. Add Playwright to the GitHub CL gate once browser install is stable.
2. Add API-backed `api-mock` E2E using `services/report/a3_api_server.mjs`.
3. Add hosted report share/revoke E2E.
4. Add admin action guardrail E2E.
5. Add screenshot review artifacts for desktop and mobile widths.
