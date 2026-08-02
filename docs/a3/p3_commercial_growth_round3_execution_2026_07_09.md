# A3 Commercial Growth Round 3 Execution - 2026-07-09

## Lane

A3 / Product Console / API-backed Dashboard / Commercial Client Surfaces.

## Opening Calibration

- Strategy bus read: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
- A1 calibration inputs: `docs/a1/**`, `services/runner/**`, `packages/sdk/**`, `packages/ts/releasefoundry/**`, A1 evidence/schema anchors.
- A2 calibration inputs: `docs/a2/**`, `services/judge/**`, `fixtures/a2/results/**`, A2 result persistence and release unblock artifacts.
- A3 baseline: PR #24 is open, draft, clean, and based on `main`; this round continues from the same A3 growth branch without modifying A1 runner logic or A2 judge semantics.

## 20 Growth Points

| ID | Growth point | Round 3 action | Evidence |
|---|---|---|---|
| R3-01 | API-backed dashboard E2E | Mounted A3 API handler into Playwright server. | `tests/e2e/static-dashboard-server.mjs` |
| R3-02 | API dashboard load proof | Browser test loads `source=api-mock` through `/api/a3/dashboard`. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-03 | Hosted report creation proof | Browser test clicks Share Hosted Report and verifies `POST /api/a3/reports/share`. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-04 | Hosted report revoke proof | Browser test revokes hosted report and verifies `POST /api/a3/reports/:reportId/revoke`. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-05 | Redacted share-link proof | Browser test requires `/r/[REDACTED_TOKEN]` instead of raw token. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-06 | API/DB surface visibility | Browser test asserts API surfaces, DB tables, and usage meters. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-07 | SaaS Admin commercial shell | Browser test asserts login, team, API keys, trust, and no real cloud write. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-08 | A1/A2 compatibility in UI | Browser test asserts A1 trace and A2 judge evidence in API-backed mode. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-09 | Static-to-API bridge | E2E server now serves static files and existing A3 API from one origin. | `tests/e2e/static-dashboard-server.mjs` |
| R3-10 | Report export to hosted report | Share/revoke path proves report center is not only local export buttons. | `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| R3-11 | Tenant/auth/RBAC/usage/audit documentation | Updated Playwright evidence doc with contract impact. | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md` |
| R3-12 | Tailwind product-system gap | Added Tailwind config, PostCSS readiness, contract doc, and tests. | `tailwind.config.ts`, `tests/a3/tailwind_boundary_contract.test.mjs` |
| R3-13 | Expo mobile release client gap | Added Expo package/app contract, release approval contract, doc, and tests. | `apps/mobile/package.json`, `tests/a3/a3_mobile_expo_client_surface.test.mjs` |
| R3-14 | WeChat mini program release client gap | Added mini program shell, release approval and incident alert pages, doc, and tests. | `apps/wechat-miniprogram/project.config.json`, `tests/a3/a3_wechat_mini_program_client_surface.test.mjs` |
| R3-15 | Admin action guardrail E2E | Kept as next browser target after API-backed base proof. | This doc |
| R3-16 | Reviewer waiver/approval E2E | Kept as next browser target after API-backed base proof. | This doc |
| R3-17 | Hosted denied-state visual E2E | Kept as next browser target for `/reports/:id` and `/r/:token`. | This doc |
| R3-18 | Mobile/desktop layout E2E | Kept as next browser target with screenshot evidence. | This doc |
| R3-19 | CL gate Playwright integration | Still not forced in CI until browser install stability is accepted. | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md` |
| R3-20 | Growth-Auditor commercial lens | This round prioritizes API-backed proof over visual-only polish. | This doc |

## API / DB / Event / Artifact Contract

- API: no new API route was added. The Playwright server now delegates existing `/api/a3/*`, `/reports/*`, and `/r/*` requests to `createA3ApiHandler(...)`.
- DB: no database migration changed. The fixture-backed A3 store remains the local API source of truth for E2E. The UI still exposes Postgres/MySQL-compatible DB contract rows.
- Event: report share/revoke events are local A3 store events only; no live billing, GitHub, ReleaseFoundry, identity, or cloud mutation runs.
- Artifact: hosted report rows are rendered through the Report Center and Artifact Registry surfaces. Raw share tokens remain redacted.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: E2E uses local `org-local` / `project-local` scope through the A3 store.
- Auth/RBAC: hosted auth is not enabled. SaaS Admin stays clean-room and plan-only for cloud operations.
- Usage: E2E asserts Usage meters are visible in API-backed mode.
- Audit: E2E verifies hosted report create/revoke evidence becomes visible through Report Center state.
- Redaction: E2E asserts redacted hosted link text and does not read `.env.local`, cookies, API keys, or tokens.

## A1 / A2 Calibration

- A1: API-backed dashboard still exposes A1 import route text and A1 trace references. No A1 runner or trace logic changed.
- A2: API-backed dashboard still exposes A2 import route text and A2 judge evidence. No A2 judge, grade, or failure taxonomy semantics changed.
- A3: this round strengthens A3 as a Product Console that can prove API-backed report lifecycle in a browser.

## Verification

```text
node --check tests/e2e/static-dashboard-server.mjs
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts
node --test tests/a3/tailwind_boundary_contract.test.mjs tests/a3/a3_wechat_mini_program_client_surface.test.mjs tests/a3/a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
```

Result:

- API-backed Playwright E2E passed: 2 pass, 0 fail.
- The earlier Windows backslash invocation failed to find tests; rerun with forward slashes succeeded.
- Client/design-surface contract tests passed: 16 pass, 0 fail.
- Commercial CL passed with 0 blockers and 0 advisories.

## Remaining Growth Targets

1. Add admin action guardrail E2E.
2. Add reviewer waiver/approval E2E.
3. Add hosted `/reports/:reportId` and `/r/:shareToken` denied-state E2E.
4. Add desktop/mobile screenshot and overflow assertions.
5. Decide when to make Playwright a blocking CL gate job.
6. Convert the contract-only Expo and WeChat shells into installable client builds once product scope approves real mobile work.
