# A3 A1/A2 Integration and Visual Pass - 2026-07-11

## Outcome

A3 now exposes one API-backed, hash-only integration matrix instead of relying on scattered compatibility claims. The matrix validates eight core schemas and seven public-safe commercial artifacts, then maps them into three operator workflows:

1. A1 runtime -> A2 judge -> A3 release console.
2. A1 object evidence -> A2 evaluation history -> A3 report center.
3. A1 billing ledger -> A2 policy -> A3 commercial sign-off.

The matrix is returned inside `a3.a1_a2_schema_drift_radar.v1` as `a3.a1_a2_integration_matrix.v1` and rendered in the A1/A2 Contract Radar.

## Upstream Sources

| Domain | Owner | Public-safe source | A3 consumer surface |
|---|---|---|---|
| Runtime route scope and quota | A1 | `docs/a1/evidence/go_route_scope_docs.json` | SaaS Runtime, usage/billing, API key admin |
| Durable billing ledger | A1 | `docs/a1/schemas/a1_billing_ledger_migration_manifest.json` | Billing migration, collections, usage/billing |
| Payment provider readiness | A1 | `docs/a1/evidence/payment_provider_readiness_public.json` | Billing admin, procurement, trust center |
| Object storage | A1 | `docs/a1/evidence/object_storage_contract_20260709.md` | Media evidence, report center, audit bundles |
| Cross-lane security | A2 | `fixtures/a2/results/a2_cross_lane_security_context.json` | Auth/RBAC, release gate, audit timeline |
| Evaluation SQL store | A2 | `fixtures/a2/results/a2_sql_store_report.json` | Case history, failure clusters, report export |
| Scenario generation backlog | A2 | `fixtures/a2/results/a2_scenario_generation_backlog.json` | Regression factory, coverage health, release war room |

Observed public-safe summary:

- 8/8 core schema contracts are compatible.
- 7/7 integration domains are aligned.
- A1 route evidence exposes 43 routes through A2 security context and 3 public route groups through route-scope docs.
- A1 payment readiness includes `wechat_pay`, `alipay`, and `stripe`, with no provider call or real charge observed.
- A1 object storage covers local filesystem and S3-compatible contracts; A3 does not claim live object readback.
- A2 SQL evidence reports 160 judge-result rows and case-history join readiness.
- A2 exposes 12 scenario candidates; A3 does not promote them because the A2 review gate forbids automatic main-pack mutation.

## Visual Changes

- Replaced the unstable auto-fit console grid with a 12-column grid and explicit two-column/full-width spans.
- Made Workflow and SaaS Runtime full-width overview surfaces.
- Reduced SaaS Runtime from roughly 6,301 px to 457 px in the API-backed desktop view.
- Converted 44 API routes, 47 DB tables, migrations, usage, billing, outbox, and guardrails into expandable detail groups.
- Added a mobile record layout for Contract Radar tables so every field remains readable without horizontal clipping.
- Preserved the quiet academic palette while improving hierarchy, density, and disclosure behavior.

## Regression Fixes

- Removed invalid `report` references from `mediaQueueRow(item)`, which previously broke official-demo media loading.
- Replaced two mojibake separators in the reviewer/code-crawl UI.
- Made Audience Filters, Workspace Groups, Environment Groups, and External Publish Blockers visible even when Report Center has no hosted reports.
- Updated the Product Console commercial-readiness test to supply the reviewer and notification contracts required for a truthful 100% fixture score.

## Verification

- Full A3 Node suite: `286 pass / 0 fail`.
- A1/A2 Python contract sample: `30 pass / 0 fail`.
- TypeScript SDK: `341 pass`; one Go HTTP vertical test was not runnable because Go is not installed in this Windows environment.
- Full Playwright suite: `18 pass / 0 fail`.
- Desktop integration screenshot: `docs/screenshots/a3-a1-a2-integration-matrix-api-backed-2026-07-11.png`.
- Mobile integration screenshot: `docs/screenshots/a3-a1-a2-integration-matrix-mobile-2026-07-11.png`.
- Runtime disclosure screenshot: `docs/screenshots/a3-runtime-contract-layout-api-backed-2026-07-11.png`.

## Ownership and Non-Claims

- A1 remains authoritative for runtime, route scopes, auth, quota, billing ledger, payment providers, and object storage.
- A2 remains authoritative for scenarios, judges, failure taxonomy, release policy, security implications, and evaluation persistence.
- A3 reads, hashes, summarizes, and displays those outputs. It does not change A1/A2 semantics.
- No real payment provider call, real charge, object-store network read, scenario promotion, or external cloud mutation was performed.
- The next architectural task remains route-level extraction of Report Center and Reviewer Workflow from the 3,853-line `app.mjs`.
