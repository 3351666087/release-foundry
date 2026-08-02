# A3 Commercial Growth Round 4 - API-Backed Review, Admin, And Denied-State E2E

## Lane

A3 / Product Console / SaaS Admin / Reviewer Workflow / Hosted Report Safety.

## Goal

Continue from latest `origin/main` after PR #24 merged. This round follows
`docs/strategy/large-saas-a1-a2-a3-full-plan.md` and focuses on browser-level
proof that A3's API-backed dashboard can exercise commercial SaaS control-plane
flows without pretending to mutate real cloud systems.

## What Changed

- Extended `tests/e2e/a3-dashboard-api-backed.spec.ts`.
- Added Playwright TS coverage for SaaS Admin action requests.
- Added Playwright TS coverage for reviewer waiver and approval receipts.
- Added Playwright TS coverage for hosted report revoked/missing denied pages.
- Added local fixture loading for redacted waiver and approval samples.
- Added same-origin API URL helper for `/api/a3/*` and `/r/*` routes.
- Hardened denied-page console checks so expected 410/404 resource messages do
  not hide unexpected browser errors.

## Twenty Growth Points Considered

1. Admin action request browser proof.
2. Admin plan-only guardrail proof.
3. Reviewer waiver API browser proof.
4. Reviewer approval API browser proof.
5. Durable review record UI refresh proof.
6. Revoked hosted report page proof.
7. Missing hosted report page proof.
8. Case-evidence leakage prevention on denied pages.
9. Expected/Actual leakage prevention on denied pages.
10. Report Center share/revoke evidence continuity.
11. API-backed same-origin bridge reuse.
12. A1 trace visibility in the API-backed dashboard.
13. A2 judge visibility in the API-backed dashboard.
14. Usage and audit visibility in the dashboard.
15. Admin plan-only mutation receipt evidence.
16. Review audit receipt evidence.
17. Hosted report access-denied event shape.
18. Redaction proof for emails and account-like values.
19. Playwright regression coverage for customer-visible flows.
20. PR-ready evidence for the next GitHub publish round.

Implemented in this round: 1 through 9, plus supporting evidence for 10 through
20 through existing A3 API/store/dashboard surfaces.

## API / DB / Event / Artifact Contract

- API: this round exercises existing routes only:
  - `POST /api/a3/admin/actions/submit`
  - `POST /api/a3/review/waivers`
  - `POST /api/a3/review/approvals`
  - `GET /api/a3/review/workflow`
  - `POST /api/a3/reports/share`
  - `POST /api/a3/reports/:reportId/revoke`
  - `GET /r/:shareToken`
- DB: the Playwright test uses the local fixture-backed A3 store mounted by the
  E2E server. It proves the UI/API contract, not production Postgres/RLS.
- Event: the flows record local audit-like receipts for admin requests, review
  records, hosted report view/revoke state, and denied-page behavior.
- Artifact: no new binary artifact is generated. Evidence is the committed E2E
  spec, this document, and the command results recorded in worklogs.

## Tenant / Auth / RBAC / Usage / Audit Impact

- Tenant: the tested dashboard source remains local `api-mock`; no real tenant
  or organization is modified.
- Auth/RBAC: SaaS Admin is still a shell/guardrail surface. Real login, SSO,
  team invites, API-key creation, billing, Trust publishing, and cloud
  mutations remain disabled or plan-only.
- Usage: this round does not change usage meters. It verifies that commercial
  flows stay reachable from the API-backed dashboard.
- Audit: waiver, approval, admin request, share, revoke, and denied-page states
  are now covered through browser-level tests.
- Secret safety: the tests assert that admin/review output does not leak
  fixture owner or teammate identity placeholders; no real secret values are read.

## A1 / A2 Calibration

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 judge, grade, score, pass/fail, release-gate, and failure-taxonomy
  semantics were not changed.
- The API-backed dashboard still starts from A1/A2-derived mock evidence and
  keeps admin/review/report control-plane evidence downstream of that evidence.
- Review records are treated as A3 governance around A1/A2 evidence, not as a
  replacement for A1 RunResult or A2 GradeResult.

## Safety Boundary

- No `.env.local` was read.
- No ReleaseFoundry API key, GitHub token, browser cookie, account email, raw signed URL,
  or private credential was read or committed.
- No live ReleaseFoundry API call was made.
- No live GitHub mutation was made.
- No real auth, billing, team, API-key, Trust, database, object-storage, or cloud
  mutation was made.
- Hosted report denied-state testing runs only against the local A3 E2E server.

## Verification

Run from the repository root:

```text
node --check tests\e2e\a3-dashboard-api-backed.spec.ts
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts
npm.cmd run test:e2e
node --test tests\a3\report_builder.test.mjs tests\a3\dashboard_wiring.test.mjs tests\a3\a3_commercial_growth_manifest.test.mjs tests\a3\tailwind_boundary_contract.test.mjs tests\a3\a3_wechat_mini_program_client_surface.test.mjs tests\a3\a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
python scripts\cl_guard.py hygiene
git diff --check
git check-ignore -v .env.local node_modules docs\screenshots\playwright-results
```

Expected result: all local checks pass, `.env.local` and transient output remain
ignored, and no real cloud/ReleaseFoundry/GitHub mutation occurs.

## Remaining Gaps

- Live GitHub Check, PR comment, and branch-protection readback still require
  maintainer-approved integration.
- Real hosted auth/RBAC/SSO and production Postgres/RLS are still future work.
- Real billing/usage export and object-storage custody are still future work.
- The current SaaS Admin flow proves safe request recording, not real cloud
  administration.
