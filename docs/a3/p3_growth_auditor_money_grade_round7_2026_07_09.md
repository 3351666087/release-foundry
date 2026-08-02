# A3 Growth-Auditor Money-Grade Round 7 - 2026-07-09

Role: Growth-Auditor / Money-Grade Auditor.

Scope: docs-only commercial audit artifact. This round intentionally changes
only this file under `docs/a3/`. Public-safe A3 docs, test names, service files,
and strategy contracts were read. No `.env.local`, raw API key, token, cookie,
signed URL, account identifier, or private cloud state was read or quoted.

## Executive Verdict

A3 is moving in the correct commercial direction. The current round is no
longer about "make the dashboard prettier"; it is about turning A3 into a
product console that can explain a release decision, prove where the evidence
came from, and show what is still blocked before the system can be sold as a
real SaaS.

Current sellable position:

```text
Sellable now: paid design-partner pilot for release evidence, review workflow,
hosted report sharing, A1/A2 evidence visibility, and commercial-readiness
planning.

Not sellable yet: production-enforced enterprise SaaS with hosted auth/RBAC,
real billing, production Postgres/RLS, live GitHub branch protection, durable
event bus, immutable object-storage custody, and full OpenAPI/SDK guarantees.
```

Round7 auditor call:

```text
The next money-grade step is to turn the current contracts into customer-facing
schemas and API-backed receipts:

OpenAPI/schema + tenant scope + event envelope + source artifact hashes
+ A1/A2 compatibility + API-backed dashboard + enterprise SaaS shell.
```

If the next implementation round only adds more UI panels, it will improve demo
breadth but not materially improve sales readiness. If it adds versioned schema,
tenant-negative proof, event/hash receipts, and A1/A2 source-hash lineage, it
will move A3 from strong prototype toward an enterprise pilot.

## Evidence Read

| Evidence area | What was checked | Signal |
|---|---|---|
| Strategy bus | `docs/strategy/large-saas-a1-a2-a3-full-plan.md` | A3 must grow as Product Console / Review Workflow / Report Center / GitHub Gate / Commercial UI / Client owner, while declaring API, DB, event, artifact, tenant, auth, RBAC, usage, audit, and A1/A2 integration impact. |
| Current A3 surface count | A3 docs, tests, services, dashboard files list | Current repo has a large A3 footprint: 100+ A3 docs, 30+ A3 tests, and 20+ A3 report/service modules. This is no longer a one-file dashboard. |
| Round6 baseline | `docs/a3/p3_growth_auditor_money_grade_round6_2026_07_09.md` | Prior verdict is still valid: sell design-partner release governance, do not claim production enterprise enforcement yet. |
| Commercial API contract | `docs/a3/p3_commercial_api_contract_2026_07_09.md`; `services/report/a3_commercial_api_contract.mjs`; `tests/a3/a3_commercial_api_contract.test.mjs` | A3 now has `a3.commercial_api_contract.v1`, 29 mapped `/v1` endpoints, endpoint status, owner lane, RBAC notes, DB tables, event names, artifact types, usage meters, and A1/A2 dependencies. |
| Event envelope | `services/report/a3_commercial_api_contract.mjs` | `releasefoundry.event_envelope.v1` is declared with ids, tenant fields, actor, request, trace, payload ref/hash, and redaction status. It is modeled, not yet a durable event bus. |
| Tenant scope | `services/report/a3_sql_migrations.mjs`; release evidence API/store tests list | SQL contract includes `organization_id` and `project_id` across core tables, plus local tenant-scope negative tests for reports and release evidence. Production RLS/auth still belongs to future hosted backend work. |
| Release evidence v2 | `services/report/a3_release_evidence.mjs`; acceptance checklist | `a3.release_evidence_summary.v2` exists with summary id/hash, A1/A2 evidence counts, GitHub readback, required-check proof, hosted report state, usage ledger, redaction, and compliance fields. |
| A1/A2 compatibility | `tests/a3/a1_a2_compatibility_contract.test.mjs`; A3 acceptance checklist | A3 preserves A1 trace/tool-call/observation fields and A2 score/pass/fail/failure-class/judge evidence in reports, hosted reports, dashboard contracts, and exports. |
| API-backed dashboard | `apps/dashboard/README.md`; `apps/dashboard/src`; E2E test list | A3 has `API-backed Mock`, local A3 API routes, hosted report lifecycle, SaaS Runtime, SaaS Admin, Enterprise Readiness, and Playwright TS coverage. This is a good local SaaS slice, not yet hosted production. |
| Enterprise SaaS shell | `docs/a3/p3_saas_admin_action_requests_2026_07_08.md`; `docs/a3/p3_billing_readiness_contract_2026_07_09.md`; acceptance checklist | Login, team, API keys, Trust, billing, usage, and cloud actions are represented as safe read-only or plan-only shells. This is correct and honest until auth/RBAC/audit providers exist. |

## Direction Evaluation

### 1. OpenAPI / Schema

Current direction is right but incomplete. A3 has many schema-versioned JSON
objects and a commercial API endpoint map, but it still lacks a customer-facing
OpenAPI package for A3-owned routes.

Good:

- `a3.commercial_api_contract.v1` maps strategy endpoints to A3 surfaces.
- `a3.release_evidence_summary.v2` creates a central authority object.
- A3 tests validate commercial contract, evidence coverage, report builder,
  API server, dashboard wiring, and A1/A2 compatibility.
- A2 already has an OpenAPI example for judge service, which gives A3 a pattern
  to follow.

Gap:

- A3 route schemas are scattered across docs, tests, service builders, and
  fixtures.
- There is no single versioned A3 OpenAPI artifact for dashboard/report/review/
  release evidence/readback/usage/admin routes.
- No generated typed client exists for A3 product surfaces.

Money-grade requirement:

```text
Add docs/a3/openapi/a3_product_console.openapi.json
and use it as the source of truth for A3 API-backed dashboard, report center,
review workflow, release evidence, usage, billing-readiness, admin guardrails,
and readback capture routes.
```

### 2. Tenant Scope

Current direction is good for a local MVP. The SQL migration contract has tenant
columns and A3 has local tenant-negative checks. But commercial SaaS requires
hosted auth middleware, DB-level isolation, and denied-state proof.

Good:

- Core contracts use `organization_id` and `project_id`.
- Report, release evidence, readback, artifact, usage, and admin action rows
  are tenant-scoped in the SQL contract.
- Cross-tenant reads are expected to return 404 or empty.

Gap:

- There is no real hosted session, actor binding, or A1 auth middleware.
- No production Postgres Row Level Security proof exists yet.
- Local SQLite/fixture-backed tenant scope is not the same as real SaaS
  isolation.

Money-grade requirement:

```text
Every A3 API response must be tested under two tenants:
same project allowed, different project denied, missing auth denied,
wrong role denied, and service-account scope restricted.
```

### 3. Event Envelope

The event direction is correct but still mostly declarative. The event envelope
fields are exactly the right kind of commercial contract: ids, tenant, actor,
request, trace, resource, payload ref, payload hash, and redaction status.

Good:

- `releasefoundry.event_envelope.v1` exists in the commercial API contract.
- A3 audit events and readback capture already store hash-like receipts in
  local flows.
- Events are linked to release evidence, reports, review, usage, billing,
  artifact, and admin surfaces.

Gap:

- There is no shared event-builder module used by all A3 write paths.
- Event publication is not durable across services.
- No event replay or event idempotency contract exists for A3 worker/CI paths.

Money-grade requirement:

```text
Create a small A3 event-envelope builder and make every A3 mutation-like local
receipt use it: report share/revoke/view, review waiver/approval, readback
capture, admin action request, release evidence snapshot, usage meter, and
artifact registry update.
```

### 4. Source Artifact Hashes

A3 is close to the right audit story, but source artifact hashes need to become
mandatory, not optional. Generated artifacts are already hashed in gate and
bundle flows. The next hardening step is to hash A1/A2 source evidence before
A3 packages it.

Good:

- Audit bundle index, generated artifact manifest, release evidence summary,
  hosted report payloads, and readback receipts already use hash concepts.
- A3 knows the difference between A1 source evidence, A2 judge evidence, and
  A3 generated output.
- Redaction firewall reduces the risk of leaking raw sensitive values.

Gap:

- A1 RunResult, TraceEvent batches, ToolCall batches, and A2 GradeResult/
  ReleaseGate/ResultPersistence inputs are not always recorded as first-class
  source artifact hash records in a shared registry.
- Some UI/report flows can show derived evidence without an obvious source hash
  join key.

Money-grade requirement:

```text
Every A3 release packet should include:
source_artifacts[] = A1 RunResult hash, A1 trace batch hash, A1 tool-call batch
hash, A2 GradeResult hash, A2 ReleaseGate hash, A2 readiness hash;
generated_artifacts[] = report hash, hosted snapshot hash, GitHub check payload
hash, PR comment hash, audit bundle hash, archive hash.
```

### 5. A1/A2 Compatibility

A3 is doing the right thing: it consumes A1/A2 outputs and does not rewrite
their meaning. The current compatibility test is valuable because it proves
trace/tool-call and judge/failure fields survive through report/export/dashboard
contracts.

Good:

- A1 fields visible in A3: run id, case id, expected/actual, trace events,
  observations, tool calls, media evidence, usage-ish counts.
- A2 fields visible in A3: scenario id, pass/fail, score, primary failure
  class, severity, judge modes, evidence readiness, release gate, persistence,
  unblock checklist.
- A3 report/export/dashboard keeps source semantics downstream-only.

Gap:

- Compatibility still relies heavily on fixture shapes and local normalized
  data.
- A3 needs stronger schema-drift tests that compare current A1/A2 schemas to
  A3 import assumptions.
- A3 should display A2 commercial blockers more prominently in the API-backed
  dashboard instead of letting them live mostly in reports.

Money-grade requirement:

```text
Add a compatibility drift gate:
if A1 changes RunResult/Trace/ToolCall or A2 changes GradeResult/ReleaseGate,
A3 import/report/dashboard tests must fail with an actionable mapping error.
```

### 6. API-Backed Dashboard

A3 has passed the important first step from static HTML to API-backed product
flow. The dashboard can load API-backed payloads, show SaaS runtime, hosted
reports, admin shell, release evidence, review workflow, and A1/A2 evidence.

Good:

- `static -> API-backed` has begun.
- Hosted report lifecycle exists locally.
- Playwright TS E2E covers meaningful browser workflows.
- Dashboard was split out from one huge HTML blob into modules.

Gap:

- It is still local API-backed, not hosted SaaS.
- The dashboard is not a full Next.js/React app yet, even though strategy says
  TypeScript + React + Next.js is the product-web direction.
- Server-state, typed route clients, component test boundaries, and hosted auth
  are not in place.

Money-grade requirement:

```text
Keep the current dashboard working, then create a Next.js/React A3 app shell
that consumes the same A3 API contract. Do not delete the existing static app
until the new app has equivalent Playwright coverage.
```

### 7. Enterprise SaaS Shell

The SaaS shell is intentionally honest. It mirrors product areas buyers expect:
login, org/project, team, usage, API keys, Trust, cloud actions, billing, and
admin requests. But most high-risk actions are plan-only or disabled, which is
correct until A1 auth/RBAC and audit enforcement exist.

Good:

- Login/team/API key/usage/trust/cloud/billing areas exist as product surfaces.
- Dangerous mutations are recorded as requests or guardrails, not fake live
  actions.
- Billing readiness is read-only and does not accidentally charge anyone.
- Admin console references A1/A2 compatibility instead of pretending A3 owns
  backend truth.

Gap:

- No real RBAC-backed admin execution.
- No SSO/OIDC/GitHub identity binding.
- No production billing provider, entitlement enforcement, invoice, or webhook.
- No enterprise trust center publish workflow with approval, audit, and rollback.

Money-grade requirement:

```text
Keep shell actions disabled until hosted auth/RBAC/audit exists, but make every
plan-only action produce a tenant-scoped, actor-bound, hash-sealed request
receipt that can later be executed by A1-owned backend services.
```

## Sellable vs Toy

| Area | Sellable now? | Why | What still feels toy-like |
|---|---|---|---|
| Release evidence dashboard | Yes, as design-partner pilot | It shows A1/A2 evidence, release gate, report, review, readback, and audit context. | Not yet backed by hosted production auth, live branch protection, or immutable object storage. |
| A1/A2 compatibility | Yes, as integration proof | Tests prove A1 trace/tool-call and A2 judge/failure fields survive A3 exports. | Needs schema-drift gates against real evolving A1/A2 contracts. |
| Hosted report lifecycle | Yes, as local governed sharing pilot | Share/revoke/denied-state behavior exists and avoids body leakage. | Needs hosted auth, immutable snapshots, expiry policy, and object-store custody. |
| Review workflow | Yes, as governance evidence pilot | Waiver/approval records are shaped and tested. | Not yet tied to real identity, cryptographic signature, or separation-of-duties enforcement. |
| Commercial API contract | Yes, as planning and sales-engineering artifact | 29 endpoints mapped to owners, surfaces, DB, event, artifact, usage, and dependencies. | Not yet a real public OpenAPI/SDK or production API gateway. |
| Event envelope | Not sellable alone | It is the right architectural direction. | Mostly contract-only; not a durable event system. |
| Source artifact hashes | Almost | Hashing exists in generated artifacts and release evidence patterns. | Source input hashes for A1/A2 evidence are not yet universal and mandatory. |
| API-backed dashboard | Yes, as local SaaS slice | Local API routes and Playwright prove product flows. | Not a deployed Next.js/React SaaS app with auth/RBAC. |
| SaaS admin shell | Demo/pilot only | Shows expected enterprise areas and safe guardrails. | Real login, API keys, team invites, Trust publish, billing, and cloud actions are blocked. |
| Usage/billing readiness | Sales conversation only | Meters and read-only billing summary exist. | No real subscription, entitlement, invoice, checkout, portal, or payment webhook. |
| Self-host/compliance | Early pilot story | SQL contracts, audit bundle, verifier, and archive docs point the right way. | No turnkey install, backup/restore, upgrade, object lock, or offline customer packet yet. |

## Tenant / Auth / RBAC / Usage / Audit Implications

| Topic | Current implication | Required commercial implication |
|---|---|---|
| Tenant | A3 contracts use `organization_id` and `project_id`; local routes can deny wrong tenant. | Every durable table, API response, report, readback, review, usage row, artifact, and event must be scoped and tested with two-tenant negative cases. |
| Auth | Current A3 is local/read-only/plan-only for risky actions. | Hosted session, service account, API key, actor id, and request id must be enforced by A1-owned middleware before live writes. |
| RBAC | Roles are declared and UI guardrails exist. | Owner/admin/developer/reviewer/auditor/billing admin permissions must be enforced server-side, with denied-state E2E proof. |
| Usage | A3 has read-only usage/billing readiness and meters. | Usage must become append-only source events, joined to release/report/review/artifact ids, then rolled into billing/chargeback. |
| Audit | A3 stores local audit/readback/review/report events. | All mutation-like actions need event envelope, actor, tenant, payload hash, source artifact hash, redaction status, and immutable retention policy. |
| Redaction | Export firewall and safety patterns exist. | Fail-closed redaction must cover JSON, Markdown, CSV, HTML, hosted reports, GitHub check, PR comment, screenshots, archive, and API errors. |

## Next Growth Points

| ID | Growth point | Owner boundary | Must land as | Why it matters |
|---|---|---|---|---|
| R7-01 | Add A3 OpenAPI artifact for product console routes. | A3 client/API contract | `docs/a3/openapi/a3_product_console.openapi.json` plus contract test. | Turns scattered schemas into customer-facing integration contract. |
| R7-02 | Add JSON Schema files for release evidence, review, report, readback, usage, admin action, and commercial API contract. | A3 schema | `docs/a3/schemas/*.schema.json` generated or checked by tests. | Prevents schema drift as code grows. |
| R7-03 | Generate a typed TS client from the A3 OpenAPI contract. | A3 web/client | Typed client used by dashboard API calls. | Moves toward strategy's TypeScript/React/Next direction. |
| R7-04 | Add compatibility drift gate for A1 RunResult. | A3 consumes A1 | Test that fails when required A1 run/case fields disappear. | Protects A3 from silently breaking on A1 changes. |
| R7-05 | Add compatibility drift gate for A1 Trace/ToolCall/Observation. | A3 consumes A1 | Schema/test mapping trace events and tool calls into A3 timeline/diff. | Keeps trace timeline and tool-call evidence reliable. |
| R7-06 | Add compatibility drift gate for A2 GradeResult. | A3 consumes A2 | Test that preserves pass/fail, score, judge mode, failure class, severity. | Keeps release gate semantics downstream-only and trustworthy. |
| R7-07 | Add compatibility drift gate for A2 ReleaseGate/CommercialReadiness. | A3 consumes A2 | Dashboard/report test showing A2 blockers prominently. | Prevents A3 from overclaiming readiness. |
| R7-08 | Make source artifact hashes mandatory. | A3 evidence packaging, A1/A2 source refs | `source_artifacts[]` in release evidence v2. | Gives audit chain a real beginning, not only generated-output hashes. |
| R7-09 | Add source hash registry entries for A1 RunResult and TraceEvent batch. | A3 artifact registry, A1 source | Artifact registry rows with source type, payload hash, redaction status. | Connects runner evidence to reports and bundles. |
| R7-10 | Add source hash registry entries for A2 GradeResult and ReleaseGate. | A3 artifact registry, A2 source | Artifact registry rows with judge version and release gate decision. | Connects judge evidence to release packets. |
| R7-11 | Implement shared A3 event envelope builder. | A3 service boundary | Small module reused by report, review, readback, admin, usage, artifact flows. | Converts event contract from doc to implementation. |
| R7-12 | Add event-envelope tests for every mutation-like local A3 route. | A3 API/store | Tests for tenant, actor, request id, payload hash, redaction status. | Builds audit trust before hosted backend exists. |
| R7-13 | Add two-tenant negative test suite across A3 API routes. | A3 API/store, A1 auth future | Same tenant allowed, wrong tenant denied, missing auth denied where applicable. | Tenant isolation is a must-have enterprise gate. |
| R7-14 | Add RBAC denied-state Playwright coverage. | A3 UI, A1 auth future | Browser tests for reviewer denied, billing admin required, auditor read-only. | Buyers need proof that UI and API do not bypass role boundaries. |
| R7-15 | Surface A2 commercial blockers in API-backed dashboard top-level status. | A3 dashboard, A2 evidence | Enterprise Readiness / Release Gate panel with explicit blocker count. | Makes blockers actionable instead of hidden in fixtures. |
| R7-16 | Convert dashboard API client to a contract-first boundary. | A3 dashboard | Client validates server response schema before rendering. | Prevents UI from rendering broken or unsafe payloads. |
| R7-17 | Start Next.js/React shell behind the same API contract. | A3 product web | Minimal app shell with run list, release evidence, report center. | Moves from static app to strategy-approved product web stack. |
| R7-18 | Keep static dashboard as compatibility reference until parity. | A3 migration safety | Playwright parity checklist between old and new app. | Avoids breaking working demo while migrating. |
| R7-19 | Add immutable hosted report snapshot hash and source-hash links. | A3 report center | Snapshot record with source hashes and generated hash. | Makes shared reports auditable after source data changes. |
| R7-20 | Add audit bundle source-hash verification. | A3 audit, A1/A2 evidence | Verifier checks source inputs and generated outputs. | Moves archive from nice export to compliance evidence. |
| R7-21 | Add readback-to-summary strict linkage. | A3 GitHub/readback | Every readback row must include `summary_id`, payload hash, provider, state. | Prevents loose GitHub evidence from being misinterpreted. |
| R7-22 | Add required-check enforcement proof fixture. | A3 GitHub, A1/A3 future integration | Redacted receipt proving enforced or explicitly not enforced. | Required before selling "blocks merge." |
| R7-23 | Add admin action request executor contract but keep executor disabled. | A3 admin UI, A1 backend future | Each action declares required role, event, rollback, audit, provider owner. | Prepares real SaaS admin safely. |
| R7-24 | Add Trust Center publish plan with approval and rollback. | A3 Trust UI, A1/A2 security | Plan-only receipt with reviewer, evidence hash, public-safe fields. | Trust page becomes governed, not decorative. |
| R7-25 | Add usage event envelope and chargeback preview. | A3 usage UI, A1 billing future | Read-only usage grouped by org/project/release/report/artifact. | Helps monetize evidence volume. |
| R7-26 | Add billing export approval workflow. | A3 billing UI, A1 billing future | Admin-approved export, no live payment mutation. | Lets team discuss revenue without unsafe checkout. |
| R7-27 | Add object-storage custody contract for media/report/archive artifacts. | A3 artifact UI, A1 storage future | Storage ref, content hash, retention class, redaction status, no signed URL. | Important for media evidence and compliance. |
| R7-28 | Add visual no-leak/no-overlap Playwright assertions for commercial pages. | A3 UI quality | Desktop/mobile screenshots plus text overflow/leak checks. | Raises product trust and demo quality. |
| R7-29 | Add self-host evidence packet checklist. | A3 enterprise UI, A1 infra | Compose smoke, migration check, verifier check, backup/restore placeholder. | Moves self-host from idea to buyer-ready package. |
| R7-30 | Add worker/CI readback dry-run contract. | A3 worker/CI, A1 infra future | CLI/worker receipt using event envelope and source hashes. | Bridges local proof to automated release governance. |

## Priority Order

1. OpenAPI/schema and source artifact hashes should come first because they
   define the contract every later feature must obey.
2. Tenant/RBAC denied-state tests should come next because no enterprise SaaS
   claim is safe without isolation proof.
3. Event envelope implementation should be added before more local mutation-like
   routes, otherwise audit shape will drift.
4. API-backed dashboard should surface A2 blockers and source hashes before
   adding more panels.
5. Next.js/React migration should start only after A3 route schemas are stable.

## Blockers

| Blocker | Why it blocks money-grade claim | Owner implication |
|---|---|---|
| No hosted auth/RBAC middleware | A3 cannot safely enable login/team/API-key/billing/trust/cloud mutations. | A1 owns backend enforcement; A3 owns UI and denied states. |
| No production Postgres/RLS proof | Local SQLite/contract tables are not enough for enterprise tenant isolation. | A1 owns production DB/RLS; A3 must keep contract and negative tests ready. |
| No public A3 OpenAPI package | Customers cannot integrate confidently and dashboard code can drift. | A3 owns product-console OpenAPI and typed client. |
| Event envelope is contract-only | Audit trail is not yet uniformly implemented. | A3 can implement local builder; A1 owns durable service event bus. |
| Source artifact hashes are not universal | Audit bundle can prove generated outputs but not always the original A1/A2 inputs. | A3 must hash source refs without changing A1/A2 semantics. |
| No live GitHub branch-protection enforcement proof | Cannot claim "ReleaseFoundry blocks merge" yet. | A3 owns readback display; A1/GitHub integration owns live enforcement plumbing. |
| No real billing provider or entitlement enforcement | Cannot charge production customers through the app. | A1 owns ledger/provider backend; A3 owns billing UI and export approval. |
| No object-storage custody proof | Media/report/archive artifacts are not production-retention ready. | A1 owns storage service; A3 owns evidence display and report/archive refs. |

## Round7 Acceptance Bar

The next implementation round should count as commercially meaningful only if
it lands at least one hard closure:

1. A3 OpenAPI + JSON Schema package with tests.
2. Mandatory source artifact hashes for A1 RunResult/Trace and A2 GradeResult/
   ReleaseGate inside release evidence v2.
3. Shared event envelope builder used by A3 local mutation-like receipts.
4. Two-tenant/RBAC denied-state tests for API-backed dashboard and report
   routes.
5. API-backed dashboard top-level A2 blocker visibility and source-hash
   visibility.

## Final Auditor Note

The team should keep the current honesty level. Do not pretend plan-only admin,
billing, Trust, team, API-key, or cloud actions are live. That restraint is a
strength, not a weakness. The commercial path is to make every local proof
contract-shaped, tenant-scoped, hash-sealed, A1/A2-compatible, and eventually
replaceable by A1-hosted backend services without changing the A3 user workflow.

