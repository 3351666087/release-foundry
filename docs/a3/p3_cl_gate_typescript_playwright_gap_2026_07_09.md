# P3 CL Gate TypeScript and Playwright Gap - 2026-07-09

Role: UI/TS/Playwright Explorer for A3.

Scope: documentation artifact only. This pass inspected `bb09c81`, with `HEAD`, local `main`, `origin/main`, and `FETCH_HEAD` all aligned to the same commit after a retry fetch of `origin main`.

Safety boundary:

- Write scope for this pass is this file only.
- Do not edit runtime code, tests, workflows, fixtures, screenshots, or generated evidence.
- Do not read `.env.local`.
- Do not call live Ashr, billing, auth, GitHub mutation, or hosted cloud APIs.
- Use clean-room official frontend evidence already committed in redacted docs/fixtures only.

## Current Repo Signals

| Surface | Mainline signal | CL automation state |
|---|---|---|
| CL gate planner | `.github/workflows/cl-gate.yml` runs `scripts/cl_guard.py plan` and `hygiene`; dashboard/docs/services/tests A3 paths trigger `a3`; `packages/ts/ashr-clone/**` triggers `typescript`; workflow/script changes force `full`. | Already in CL. |
| A3 Node contracts | `a3-node` runs `node --test tests/a3/*.mjs` when A3/evidence paths change. | Already in CL. |
| TypeScript package | `packages/ts/ashr-clone` has strict `tsconfig.json`, declaration output, `npm test = npm run build && node --test test/*.test.mjs`, and CI `typescript-sdk` job with `npm ci`. | Already in CL for TS-package changes only. |
| Dashboard webapp | Static HTML/CSS/MJS app: `index.html` 500 lines, `app.mjs` about 2.8k nonblank lines, `styles.css` about 1k nonblank lines, plus four small components and an untyped browser API client. | Covered by source-string wiring tests, not browser execution. |
| Tailwind/CSS | No `tailwind.config.*`, `postcss.config.*`, Vite config, root `package.json`, or dashboard package was found. Styling is hand-authored CSS. | Not in CL beyond A3 string tests. |
| Playwright | No `playwright.config.*`, Playwright package, E2E specs, screenshot assertions, or browser CI job was found. | Missing. |
| Dashboard/admin/billing/review | API/server and service tests cover admin action guardrails, usage/billing read-only state, review waiver/approval records, share/revoke, report center, artifact registry, and release evidence. Dashboard tests prove wiring by regex. | Logic in CL; browser workflow not in CL. |
| Official frontend parity | Clean-room docs/fixtures cover official mirror/code-crawl/page-state backlog. Results visual parity for dataset `884` / run `11926` is still explicitly pending. | Logic/report wiring in CL; logged-in official visual parity is next/manual. |

## CL Now vs Next

Already automated in CL now:

- selective planning and hygiene: `python scripts/cl_guard.py plan ...` and `python scripts/cl_guard.py hygiene`
- A3 Node contracts on A3 changes: `node --test tests/a3/*.mjs`
- TypeScript SDK build/tests on TS package changes: `npm ci` then `npm test` in `packages/ts/ashr-clone`
- pinned A3 evidence verification on evidence changes

Can be automated in CL now with existing tools and no new dependencies:

- dashboard JS syntax checks with `node --check`
- focused A3 dashboard/admin/review/report tests as named workflow steps
- source-level CSS quality tests implemented with `node:test`
- CL planner unit coverage for dashboard, docs, TypeScript, workflow, and evidence path routing
- official clean-room fixture/redaction assertions using existing Node tests

Requires next tooling before CL can enforce it honestly:

- Playwright TS E2E, screenshots, console-error checks, mobile/desktop overflow checks, and click workflows
- dashboard TypeScript migration or a generated typed dashboard API client
- Tailwind/PostCSS/stylelint pipeline if the dashboard moves away from hand-authored CSS
- official Results visual parity from a logged-in Ashr browser session

## Executable Growth Checks

`Automate` means where the check should live once implemented. `Now` means the command either already exists or can be added with the current runtime stack. `Next` means the named command is concrete but requires adding the referenced test/tool first.

| ID | Area | Executable check | Command | Automate |
|---|---|---|---|---|
| CL-01 | CL routing | A dashboard source/CSS change sets `a3=true` and not `typescript=true`. | `python -m pytest tests/a3/test_cl_guard_plan_dashboard.py -q` | Now |
| CL-02 | CL routing | A `docs/a3/**` change runs A3 Node contracts but not TS/Go/Rust. | `python -m pytest tests/a3/test_cl_guard_plan_docs_a3.py -q` | Now |
| CL-03 | CL routing | A `packages/ts/ashr-clone/**` change sets `typescript=true`. | `python -m pytest tests/a3/test_cl_guard_plan_typescript.py -q` | Now |
| CL-04 | CL routing | Workflow or `scripts/cl_guard.py` changes force `full=true`. | `python -m pytest tests/a3/test_cl_guard_plan_full.py -q` | Now |
| CL-05 | Hygiene | Secret, private path, and pinned A3 artifact line-ending blockers remain clean without reading `.env.local`. | `python scripts/cl_guard.py hygiene` | Already |
| TS-01 | TypeScript mainline | Strict compile and declaration generation for the SDK. | `cd packages/ts/ashr-clone && npm ci && npm run build` | Already |
| TS-02 | TypeScript mainline | Full SDK parity tests stay green after build. | `cd packages/ts/ashr-clone && npm ci && npm test` | Already |
| TS-03 | TypeScript mainline | Published package metadata still exposes all bins and declarations. | `cd packages/ts/ashr-clone && npm ci && npm pack --dry-run` | Now |
| TS-04 | Typed client | SaaS client HTTP wrappers, release gate, audit log, release evidence, and OpenAPI route parity stay typed and tested. | `cd packages/ts/ashr-clone && npm ci && node --test test/saas-release-parity.test.mjs test/saas.test.mjs` | Already |
| TS-05 | Typed client | Official/Ashr API dry-run client keeps mutating calls dry-run-first and redacted. | `cd packages/ts/ashr-clone && npm ci && node --test test/api-client.test.mjs test/probe.test.mjs` | Already |
| TS-06 | Typed dashboard client | Add generated or hand-authored dashboard API DTO types for `/api/a3/dashboard`, admin, review, report center, and artifact registry. | `cd apps/dashboard && npm run typecheck` | Next |
| UI-01 | Dashboard syntax | Browser MJS modules parse before source-string tests run. | `node --check apps/dashboard/src/app.mjs && node --check apps/dashboard/src/api-client.mjs` | Now |
| UI-02 | Dashboard syntax | Component modules parse. | `node --check apps/dashboard/src/components/saas-runtime-panel.mjs && node --check apps/dashboard/src/components/saas-admin-console.mjs && node --check apps/dashboard/src/components/product-console-panel.mjs && node --check apps/dashboard/src/components/enterprise-readiness-panel.mjs` | Now |
| UI-03 | Dashboard wiring | Existing dashboard source contracts continue to cover selectors, fixtures, exports, official parity, admin, review, release evidence, and enterprise panels. | `node --test tests/a3/dashboard_wiring.test.mjs` | Already |
| UI-04 | Dashboard API workflow | API-backed dashboard, admin action requests, review workflow, share/revoke, report center, billing-disabled usage ledger, and product console routes stay compatible. | `node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_saas_admin.test.mjs tests/a3/a3_review_workflow.test.mjs` | Already |
| UI-05 | Exports | JSON/CSV/Markdown/print report exports include A3 evidence without leaking secrets. | `node --test tests/a3/report_builder.test.mjs tests/a3/export_firewall_generated_artifacts.test.mjs` | Already |
| CSS-01 | CSS quality | No viewport-scaled font sizes, negative letter spacing, excessive card radius, or horizontal overflow-prone fixed widths enter `styles.css`. | `node --test tests/a3/dashboard_css_quality.test.mjs` | Now |
| CSS-02 | CSS quality | Mobile media query covers shell, metrics, console grid, ops grid, detail grid, diff grid, and workflow. | `node --test tests/a3/dashboard_css_responsive_contract.test.mjs` | Now |
| CSS-03 | CSS quality | Print CSS hides interactive controls and leaves report preview printable. | `node --test tests/a3/dashboard_print_css_contract.test.mjs` | Now |
| CSS-04 | Tailwind boundary | Until Tailwind is introduced, the repo must not grow orphan Tailwind/PostCSS config or unused class-only styling promises. | `node --test tests/a3/tailwind_boundary_contract.test.mjs` | Now |
| CSS-05 | Tailwind pipeline | If Tailwind is adopted, content scanning, CSS build, and class safelist must be part of dashboard CI. | `cd apps/dashboard && npm run lint:css && npm run build:css` | Next |
| PW-01 | Playwright setup | Add a TS Playwright config with local static server and A3 API server projects. | `cd apps/dashboard && npx playwright test --config=playwright.config.ts --list` | Next |
| PW-02 | Playwright smoke | Static mock source loads without console errors and renders overview metrics, run list, case detail, and export buttons. | `cd apps/dashboard && npx playwright test tests/e2e/dashboard-static.spec.ts` | Next |
| PW-03 | Playwright API-backed | `source=api-mock` loads from `services/report/a3_api_server.mjs`, then renders SaaS Runtime, Report Center, Product Console, Admin, and Reviewer Workflow. | `cd apps/dashboard && npx playwright test tests/e2e/dashboard-api-backed.spec.ts` | Next |
| PW-04 | Playwright admin/billing | Admin actions show read-only/plan-only receipts; usage/billing remains read-only and no real billing/team/API-key mutation button becomes enabled. | `cd apps/dashboard && npx playwright test tests/e2e/admin-billing-guardrails.spec.ts` | Next |
| PW-05 | Playwright review | Reviewer Workflow shows lanes/items/records and can refresh after API waiver/approval submission. | `cd apps/dashboard && npx playwright test tests/e2e/reviewer-workflow.spec.ts` | Next |
| PW-06 | Playwright reports | Share hosted report, revoke it, verify Report Center and denied hosted report states render without body leakage. | `cd apps/dashboard && npx playwright test tests/e2e/hosted-report-lifecycle.spec.ts` | Next |
| PW-07 | Playwright layout | Desktop and mobile screenshots assert no blank panels, no horizontal overflow, no overlapping key text, and stable panel heights. | `cd apps/dashboard && npx playwright test tests/e2e/dashboard-layout.spec.ts` | Next |
| PW-08 | Playwright official demo | `source=p3-official-demo` renders dataset `884` / run `11926`, media evidence, official mirror, code crawl, parity roadmap, and visual-results-pending language. | `cd apps/dashboard && npx playwright test tests/e2e/official-demo-parity.spec.ts` | Next |
| A3-01 | Admin/review/billing | A3 API server keeps billing mutations disabled, admin action requests durable, and review waiver/approval records sanitized. | `node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_saas_admin.test.mjs tests/a3/a3_review_workflow.test.mjs` | Already |
| A3-02 | Billing usage | Ledger-backed billing-adjacent fields cover runs, cases, reports, retained bytes, readbacks, verifier runs, and hosted views without enabling billing mutations. | `node --test tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/billing_usage_release_evidence.test.mjs` | Next |
| A3-03 | Official parity | Official mirror/code-crawl/page-state reports remain clean-room and never commit source snippets, cookies, tokens, emails, or raw signed URLs. | `node --test tests/a3/report_builder.test.mjs tests/a3/official_frontend_cleanroom_contract.test.mjs` | Next |
| A3-04 | Official parity | Dashboard distinguishes `api_visible`, `visual_pending`, `visual_confirmed`, and `out_of_scope` for official frontend parity. | `node --test tests/a3/dashboard_wiring.test.mjs tests/a3/official_frontend_page_state.test.mjs` | Next |
| A3-05 | Official parity | Official Results visual parity remains blocked until a logged-in browser confirms run `11926` in the Results tab. | `node --test tests/a3/official_results_visual_state.test.mjs` | Next |
| A3-06 | Release evidence | Release Evidence, War Room, Report Center, hosted reports, PR Gate, and Artifact Registry share one authority object. | `node --test tests/a3/report_builder.test.mjs tests/a3/artifact_registry.test.mjs tests/a3/report_center_index.test.mjs` | Already |
| A3-07 | Export safety | Generated A3 docs/fixtures and dashboard exports fail closed on raw tokens, cookies, emails, account paths, and signed URLs. | `node --test tests/a3/export_firewall_generated_artifacts.test.mjs` | Already |
| A3-08 | Dashboard package boundary | Introduce `apps/dashboard/package.json` only when it owns lint/typecheck/e2e scripts and no secret-bearing env is required. | `cd apps/dashboard && npm ci && npm run lint && npm run test:e2e` | Next |

## Recommended CL Gate Additions

Near-term, no new dependencies:

1. Add dashboard syntax checks to the `a3-node` job:

```bash
node --check apps/dashboard/src/app.mjs
node --check apps/dashboard/src/api-client.mjs
for f in apps/dashboard/src/components/*.mjs; do node --check "$f"; done
```

2. Add Python unit coverage for `scripts/cl_guard.py build_plan(...)` so path routing is tested without needing synthetic git diffs.

3. Add source-level CSS tests under `tests/a3/` for responsive contracts, print CSS, and banned fragile CSS patterns.

4. Keep `typescript-sdk` scoped to `packages/ts/ashr-clone/**`, but add `npm pack --dry-run` once package shape becomes customer-facing.

Next tooling lane:

1. Add `apps/dashboard/package.json`, `playwright.config.ts`, and TS E2E specs.

2. Run Playwright only when `apps/dashboard/**`, `services/report/**`, `tests/a3/**`, or official-parity fixtures change.

3. Add typed dashboard DTOs before migrating `apps/dashboard/src/api-client.mjs` to TypeScript; otherwise TypeScript coverage remains limited to the SDK package.

4. Add Tailwind only if it replaces enough hand CSS to justify a build step; otherwise keep CSS quality as source tests plus Playwright layout assertions.

## Acceptance Criteria for the Next CL Gate Round

- Dashboard syntax, source wiring, CSS quality, A3 API/admin/review contracts, and export firewall checks run on every dashboard or A3 report change.
- TypeScript SDK changes run `npm ci`, strict build, Node tests, and package dry-run.
- Playwright TS E2E covers static, API-backed, official-demo, admin/billing guardrail, review workflow, hosted report lifecycle, desktop, and mobile flows.
- Official frontend parity is represented as clean-room states; visual Results parity stays pending until logged-in browser evidence exists.
- Billing, API keys, team invites, OAuth/session, Trust publish, checkout, portal, and destructive cloud mutations remain disabled or plan-only unless a separate production-auth round approves them.
