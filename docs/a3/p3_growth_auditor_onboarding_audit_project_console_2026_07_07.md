# A3 Growth Auditor - Onboarding, Audit Log, Project Console - 2026-07-07

## Auditor Verdict

This round moves A3 closer to a sellable SaaS product because it adds the missing customer workflow layer between raw eval evidence and enterprise purchase value:

- onboarding tells a new user how to reach first value,
- project console gives an owner a release status surface,
- audit log gives reviewers and compliance teams a record of what happened,
- commercial readiness explains whether the evidence is strong enough to sell or demo.

This is still not the final commercial product because auth, persistent SQL audit logs, billing enforcement, project creation, and real reviewer actions remain plan-only. But it is materially less toy-like than a static dashboard because the workflow state is API-backed and derived from A1/A2/report evidence.

## New Sellable Capabilities

| Capability | Why It Can Sell | Buyer Value |
|---|---|---|
| Product Console API | Gives the dashboard a single workflow object for onboarding, project state, audit state, and commercial readiness. | Buyers see a product workflow, not a pile of JSON fixtures. |
| Onboarding checklist | Shows first-run, judge attach, triage, hosted report, release gate, reviewer, usage, and audit steps. | New users can understand how to reach value without training. |
| Project Console summary | Aggregates runs, cases, failures, reports, usage, and actions into a project-level control surface. | Engineering managers can scan release health quickly. |
| Audit Log summary | Turns import, report, share-link, and report-center events into redacted audit evidence. | Security/compliance teams get a credible review trail. |
| Commercial Readiness score | Measures A1 trace, A2 judge, project, hosted report, usage, and audit readiness. | Sales and leadership can tell whether a tenant is demo/sellable. |
| API route `/api/a3/product/console` | Lets external app pages consume the same object without duplicating frontend logic. | Makes SaaS webapp migration easier. |
| Dashboard Product Console panel | Adds visible onboarding/project/audit workflow to the UI. | The product feels closer to a real control tower. |
| A1/A2 compatibility bridge | Product console consumes normalized A1 trace and A2 judge evidence. | Reduces risk that A3 drifts away from A1/A2. |
| Empty-project honesty | Empty projects show setup-required and missing evidence instead of fake success. | Avoids demo deception and supports real onboarding. |
| Redacted audit policy | Audit log explicitly states redacted-only payload policy. | Reduces enterprise security objections. |

## Toy-Like Gaps To Upgrade

| Gap | Why It Is Toy-Like | Upgrade Requirement |
|---|---|---|
| Audit events are still memory/file backed | They disappear without durable store. | Persist to SQL `audit_events` with tenant scope. |
| No real auth | Product console cannot enforce permissions. | Connect hosted session and RBAC middleware. |
| No real project creation flow | Project exists as local contract. | Add tenant-scoped project CRUD from A1. |
| No real reviewer action | Review/waiver/approval are represented elsewhere but not mutating here. | Add workflow APIs with signed approval records. |
| Usage budget is read-only | Customers cannot set limits. | Add quota policy and billing plan backend. |
| Report Center is local API only | Not hosted as customer-facing SaaS page yet. | Host share/report center with auth and tenant route. |
| No E2E onboarding test | Unit/wiring tests prove shape but not user journey. | Add Playwright path: select API source -> create report -> product console updates. |
| No official frontend re-check this round | Uses prior clean-room observations. | Re-open ReleaseFoundry frontend/API docs and compare onboarding/settings copy. |

## Why Customers Pay

Customers do not pay for a dashboard alone. They pay when the product reduces release risk and creates review evidence.

This round supports that by:

1. reducing time to first value with onboarding state,
2. making release health visible at project level,
3. turning report/share/import actions into audit signals,
4. linking technical evidence to commercial readiness,
5. preserving redaction and no-secret boundaries.

## Enterprise / Self-Host / Audit Value

- Enterprise: shows team-ready workflow surfaces before real auth lands.
- Self-host: product console can be backed by the same DB contract and API store.
- Audit: audit log object is redacted and event-type oriented.
- Compliance: commercial readiness identifies missing approval, waiver, and API-key events.
- Expansion: onboarding completion, report creation, usage meters, and audit events become future paid metrics.

## At Least 20 Next Growth Points

| ID | Growth Point | Parallel Lane | Must Land |
|---|---|---|---|
| OAPC-01 | Persist product console audit events to SQL. | API/DB | migration + tests |
| OAPC-02 | Add `GET /api/a3/projects/:projectId/console`. | API | route + tests |
| OAPC-03 | Add project list page fed by API store. | UI | component + wiring test |
| OAPC-04 | Add onboarding route with three paths: upload JSON, Python SDK, GitHub Action. | UI | panel + E2E |
| OAPC-05 | Add create-project plan route, still no real mutation. | API | guarded action plan |
| OAPC-06 | Add audit event export to hosted report manifest. | Report | manifest test |
| OAPC-07 | Add report-center event timeline. | UI | timeline rows |
| OAPC-08 | Add reviewer action placeholders into product console. | Workflow | action contract |
| OAPC-09 | Add waiver/approval event ingestion into audit log. | API | schema + tests |
| OAPC-10 | Add billing/quota read-only plan card. | UI/Usage | component |
| OAPC-11 | Add official ReleaseFoundry settings/onboarding parity note. | Evidence | redacted doc |
| OAPC-12 | Add Playwright screenshot of Product Console. | Evidence | screenshot |
| OAPC-13 | Add product console section to JSON export. | Report | export test |
| OAPC-14 | Add product console Markdown executive section. | Report | markdown test |
| OAPC-15 | Add tenant scope mismatch tests. | Security | store/API tests |
| OAPC-16 | Add audit-log redaction firewall checks. | Security | generated artifact scan |
| OAPC-17 | Add API-key rotation event to audit examples without secrets. | Admin | fixture + tests |
| OAPC-18 | Add onboarding completion meter to usage ledger. | Billing | ledger test |
| OAPC-19 | Add GitHub Action onboarding evidence row. | Integration | fixture/doc |
| OAPC-20 | Add production readiness blocker if no audit log exists. | Gate | readiness test |
| OAPC-21 | Add project environment switcher: dev/staging/prod. | UI/API | contract + tests |
| OAPC-22 | Add self-host console mapping for product console routes. | Enterprise | doc + contract test |
| OAPC-23 | Add reviewer SLA fields to project console. | Workflow | model + UI |
| OAPC-24 | Add retention policy preview tied to audit/report events. | Compliance | model + tests |

## Most Money-Adjacent Direction

The closest path to money after this round is:

1. PR Gate + Product Console, because release blockers enter engineering workflow.
2. Enterprise Audit + Report Center, because evidence and audit trails support procurement.
3. Self-host + SQL persistence, because enterprise buyers need data control.
4. Usage/Billing, because onboarding/report/audit events create durable paid meters.

The next round should parallelize Project Console persistence, product console export, and Playwright screenshot evidence.
