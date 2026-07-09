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
  - `tests/e2e/a3-dashboard-api-backed.spec.ts`
- The E2E suite serves the real `apps/dashboard/index.html` shell and checks visible product surfaces, not a stub page.
- Hardened the local static server for browser-style asset loading with `clientError`, file-stream error, and response error handling.
- Mounted the local A3 API handler into the E2E server so `source=api-mock` exercises real `/api/a3/*`, `/reports/*`, and `/r/*` routes during browser tests.

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
- API-backed dashboard loading
- Hosted report share/revoke lifecycle
- Raw A2 source switching

## API / DB / Event / Artifact Contract

- API: no new API route was added. E2E now mounts the existing `services/report/a3_api_server.mjs` handler and asserts dashboard-visible A3 surfaces for `GET /api/a3/dashboard`, A1/A2 import routes, product console, review workflow, report center, admin console, and artifact registry. It also exercises `POST /api/a3/reports/share` and `POST /api/a3/reports/:reportId/revoke`.
- DB: E2E checks the existing dashboard-visible DB contract language, including tenant/project context, `team_members`, `api_keys`, and usage-meter rows. It does not open a DB connection or write data.
- Event: no production event is emitted. The API-backed hosted report test records local report share/revoke audit state through the existing fixture-backed A3 store only.
- Artifact: successful E2E saves `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`; transient Playwright traces/screenshots stay under ignored `docs/screenshots/playwright-results/`. Hosted report rows render redacted `/r/[REDACTED_TOKEN]` paths.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: E2E verifies dashboard-visible tenant/project strings on the Product Console (`org-local` / `project-local`).
- Auth/RBAC: E2E verifies SaaS Admin and RBAC Matrix visibility, but does not perform hosted login or mutate identities.
- Usage: E2E verifies Usage meters are visible in the SaaS Runtime panel.
- Audit: E2E verifies Report Center, Release Evidence, Reviewer Workflow, Enterprise Readiness, hosted report sharing, and hosted report revocation surfaces are visible.
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
- Final static/official-demo verification: `npx.cmd playwright test` passed 4/4 tests in Chromium.
- API-backed verification: `npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts` passed 5/5 tests in Chromium after Round 4 added SaaS Admin guardrail, reviewer waiver/approval receipt, and hosted report denied-state coverage.
- NPM script verification should now run both static and API-backed E2E specs.
- Screenshot evidence: `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`.
- CI should install browsers explicitly before running this lane.

## Failure Points Observed

- PowerShell script execution policy blocks bare `npm` / `npx` shims on this workstation; `.cmd` shims work.
- Fresh Playwright installs need `npx playwright install chromium` before browser-backed tests can run.
- Early assertions were corrected to match the real dashboard text: official-demo case IDs, first-page DB table slice, and `major` triage severity.
- The local static server needed stream/client error handling to avoid intermittent connection refusal during browser runs.

## Next Growth

1. Add Playwright to the GitHub CL gate once browser install is stable.
2. Add screenshot review artifacts for desktop and mobile widths.
3. Add live-auth RBAC E2E after A1/A3 auth middleware exists.
4. Add production Postgres/RLS-backed E2E after the SaaS store is real.
5. Add maintainer-approved live GitHub readback E2E after CI credentials exist.

## Round 4 Follow-Up - Review/Admin/Denied-State

- Added SaaS Admin action guardrail E2E for plan-only login/team/API-key/trust/cloud-management style operations.
- Added reviewer waiver and approval API-backed E2E using existing redacted A3 governance fixtures.
- Added durable review-record UI assertions for waiver count, approval count, status, and `hash_sealed` custody language.
- Added hosted report denied-state E2E for revoked and missing share-token pages.
- Added no-leak assertions that denied pages do not render `Case Evidence`, `Expected`, or `Actual` report body details.
- Kept the test local and fixture-backed; it does not call live Ashr, GitHub, billing, hosted auth, team, API-key, Trust, or cloud mutation APIs.
