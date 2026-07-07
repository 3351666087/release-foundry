# P3 A3 SaaS API And DB Migration Draft - 2026-07-07

Author: A3 SaaS Migration Planner
Scope: commercial migration draft only. This pass adds documentation under `docs/a3` and does not change runtime code, tests, fixtures, schemas, or secret-bearing files. `.env.local` is intentionally out of scope and must not be read, printed, copied, or referenced for values.

## Executive Summary

A3 is ready to move from a local, static dashboard and mock-fixture workflow toward a SaaS-grade, API-backed reporting product. The migration should preserve A1 runner evidence, A2 judge output, and current A3 report semantics while adding durable storage, hosted report sharing, authenticated API access, and repeatable verification evidence.

The recommended target is:

- Frontend: componentized app shell, initially framework-neutral or Vite/React if the team chooses a modern component stack.
- Backend: typed HTTP API that serves runs, cases, scores, traces, report metadata, and hosted report assets.
- Database: PostgreSQL for production, SQLite for local/offline developer mode, MySQL only if an existing commercial constraint requires it.
- Report distribution: shareable hosted reports with signed access, immutable report snapshots, redaction firewall, and export audit trails.
- Contracts: additive A3 adapters that continue accepting A1 local run results, A2 grade results, current A3 fixtures, and official API-shaped run data.
- Security: no secrets in static bundles, fixtures, logs, report exports, or hosted report URLs.

## Migration Goals

- Replace static-only dashboard state with API-backed data loading.
- Replace mock fixture dependence with database-backed run and report data.
- Replace the single HTML blob pattern with maintainable app components.
- Replace local-only export downloads with hosted, shareable report pages and controlled export artifacts.
- Preserve A1/A2/A3 compatibility through versioned contracts and adapter tests.
- Provide verification evidence suitable for release review, customer trust review, and regression triage.

## Non-Goals For This Draft

- This draft does not require immediate removal of static fixtures.
- This draft does not require changing A1 runner behavior or A2 judge semantics.
- This draft does not define production cloud vendor selection.
- This draft does not include any secret values, environment file content, cookies, API keys, tokens, or account identifiers.

## Current State

Current A3 has useful foundations:

- A3 dashboard/report behavior can consume normalized A1/A2/A3 evidence.
- Static fixtures and sanitized API probes provide populated run, case, score, and failure evidence.
- Export redaction firewall work already exists in the report path.
- The dashboard has already started moving away from a very large HTML file toward a smaller webapp shell.

Main gaps before SaaS readiness:

- Data is still mostly local/static rather than served by a product API.
- Mock fixtures are useful for tests, but are not a durable source of customer state.
- Report exports are local artifacts, not product-hosted reports with access control.
- There is not yet a production database model for runs, cases, traces, reports, report views, exports, or share links.
- Verification evidence is spread across docs, tests, and fixtures instead of being promoted into a first-class migration gate.

## Target Architecture

```text
Browser App
  |
  | HTTPS, authenticated API calls
  v
A3 API Service
  |-- Contract adapters: A1 RunResult, A2 GradeResults, A3 normalized report, official API-shaped runs
  |-- Report builder and redaction firewall
  |-- Hosted report renderer
  |-- Export worker
  v
PostgreSQL
  |-- runs
  |-- cases
  |-- judge_results
  |-- trace_events
  |-- report_snapshots
  |-- report_exports
  |-- share_links
  |-- audit_events

Object Storage
  |-- redacted report bundles
  |-- signed media references
  |-- immutable export files
```

## Database Choice

### Recommendation

Use PostgreSQL for production and SQLite for local development. Defer MySQL unless a hosted platform, customer, or existing company standard requires it.

### Rationale

| Option | Best Use | Strengths | Risks |
|---|---|---|---|
| PostgreSQL | Production SaaS | Strong JSON support, indexing, relational integrity, migrations, row-level security options, common managed hosting | Slightly heavier local setup than SQLite |
| SQLite | Local development, tests, offline demos | Zero-service setup, fast test isolation, easy fixture replay, good for beginner workflows | Not a fit for multi-user SaaS concurrency, background workers, or hosted report traffic |
| MySQL | Existing infra constraint | Mature managed hosting, familiar operational model, good relational support | JSON/query ergonomics and migration patterns are less convenient for trace-heavy report data |

### DB Policy

- Production source of truth: PostgreSQL.
- Local smoke tests: SQLite.
- Contract fixtures: retained for regression only, not treated as product state.
- JSON payloads: store raw source envelopes for traceability, but expose normalized fields through typed tables and API DTOs.

## Core Data Model Draft

| Table | Purpose | Key Fields |
|---|---|---|
| `runs` | A1/A2/A3 run identity and aggregate status | `id`, `source_kind`, `source_run_id`, `dataset_id`, `runner_id`, `status`, `started_at`, `ended_at`, `raw_payload_hash` |
| `cases` | Per-case execution and display data | `id`, `run_id`, `case_id`, `scenario_id`, `title`, `status`, `latency_ms`, `expected_json`, `actual_json` |
| `judge_results` | A2 and A3 grading output | `id`, `case_id`, `passed`, `score`, `primary_failure_class`, `severity`, `judge_modes`, `raw_payload_hash` |
| `trace_events` | Replay, observation, and timeline evidence | `id`, `run_id`, `case_id`, `seq`, `event_type`, `phase`, `source`, `timestamp`, `redacted_payload_json` |
| `media_evidence` | Signed or redacted evidence references | `id`, `case_id`, `kind`, `mime_type`, `storage_key`, `redaction_status`, `expires_at` |
| `report_snapshots` | Immutable hosted report state | `id`, `run_id`, `snapshot_version`, `builder_version`, `redaction_policy_version`, `content_hash` |
| `report_exports` | Generated JSON, Markdown, CSV, PDF, or bundle output | `id`, `report_snapshot_id`, `format`, `storage_key`, `created_by`, `created_at`, `content_hash` |
| `share_links` | Hosted report sharing | `id`, `report_snapshot_id`, `scope`, `expires_at`, `revoked_at`, `created_by`, `last_viewed_at` |
| `audit_events` | Operational and trust evidence | `id`, `actor_id`, `event_type`, `object_type`, `object_id`, `created_at`, `metadata_json` |

## API Surface Draft

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/a3/runs` | List runs with filters | Supports dataset, status, date range, source kind, failure class |
| `POST /api/a3/runs/import` | Import A1/A2/A3/official API-shaped payloads | Uses contract adapters and stores raw payload hash |
| `GET /api/a3/runs/{runId}` | Run summary | Includes aggregate metrics and case summary counts |
| `GET /api/a3/runs/{runId}/cases` | Case list | Paginates and filters by pass/fail/failure class |
| `GET /api/a3/cases/{caseId}` | Case detail | Expected vs actual, tool calls, trace summary, media references |
| `GET /api/a3/cases/{caseId}/trace` | Timeline evidence | Supports replay-focused pagination |
| `POST /api/a3/reports` | Build immutable report snapshot | Requires redaction firewall result before publish |
| `GET /api/a3/reports/{reportId}` | Hosted report model | Returns redacted app-ready component data |
| `POST /api/a3/reports/{reportId}/exports` | Generate export artifact | Async when PDF/bundle generation is slow |
| `POST /api/a3/reports/{reportId}/share-links` | Create share link | Supports expiry, revocation, and access scope |
| `GET /r/{shareToken}` | Public or restricted hosted report | Never leaks database ids or secret values |

## Migration Phases

### Phase 0: Baseline And Guardrails

- Freeze current A3 normalized report contract as a compatibility fixture.
- Create redaction test cases for token-like strings, formula injection, URLs, headers, cookies, and account identifiers.
- Add a migration evidence index that records commands, inputs, output paths, and pass/fail summaries.
- Define allowed import sources and reject unknown source envelopes by default.

### Phase 1: Static To API-Backed

- Serve current static fixture data through the new API without changing frontend behavior.
- Add frontend loading, empty, error, and stale-data states.
- Add server-side pagination for runs, cases, and trace events.
- Add API snapshot tests proving frontend DTOs match the current A3 normalized model.

### Phase 2: Mock Fixture To DB Data

- Add import jobs that write normalized A1/A2/A3 payloads into the database.
- Keep fixtures for regression, but make DB reads the default app path.
- Add idempotent imports using content hashes and source ids.
- Add schema migrations with forward and rollback checks in CI.

### Phase 3: HTML Blob To Components

- Split the dashboard into route-level views: Runs, Run Detail, Case Detail, Report, Export Queue, Share Settings.
- Convert repeated UI areas into owned components: score summary, failure table, evidence timeline, expected/actual diff, tool-call viewer, redaction status, export status.
- Keep component inputs aligned to API DTOs instead of reading raw fixture shapes directly.
- Add screenshot or DOM-level smoke checks for the most important views.

### Phase 4: Local Export To Hosted Report

- Store immutable report snapshots before export generation.
- Render shareable hosted report pages from report snapshots.
- Generate exports from the same snapshot used by the hosted report.
- Add share link expiry, revocation, audit event logging, and access checks.

### Phase 5: Production Hardening

- Add auth, tenant scoping, rate limits, import quotas, and export job isolation.
- Add observability for import latency, report build latency, export latency, redaction failures, and share-link views.
- Add customer-safe retention policies for raw payloads, traces, media references, and generated exports.
- Add release gates that block publish when compatibility, redaction, or hosted-report evidence is missing.

## Actionable Growth Points

| ID | Growth Point | Execution Step | Success Evidence |
|---|---|---|---|
| GP-01 | Static dashboard data loader | Add a `runs` API loader and route current dashboard state through it | Dashboard renders same run counts from `GET /api/a3/runs` as from static fixtures |
| GP-02 | API DTO contract | Define `RunSummaryDto`, `CaseSummaryDto`, `CaseDetailDto`, and `ReportSnapshotDto` | Contract tests compare DTOs to current normalized A3 report output |
| GP-03 | Loading and error states | Add visible non-blocking loading, empty, retry, and API error states | UI smoke test covers success, empty, 500, and network timeout responses |
| GP-04 | Fixture import command | Build an import path for sanitized A1/A2/A3 fixtures | Import command writes rows and prints only counts, ids, and hashes |
| GP-05 | Idempotent DB imports | Use source ids plus content hashes to prevent duplicate runs | Re-importing the same payload changes zero rows except audit metadata |
| GP-06 | DB-backed run list | Replace fixture array reads with paginated DB queries | Run list supports dataset, status, date, and failure class filters |
| GP-07 | DB-backed case detail | Store expected, actual, tool calls, observations, and trace links per case | Case detail page matches static fixture rendering on golden examples |
| GP-08 | Trace pagination | Store trace events separately from case summary records | Large traces load in pages without blocking case summary render |
| GP-09 | Media evidence references | Store redacted metadata and storage keys, not raw signed URLs in app state | API responses omit secret-bearing URLs until an authorized fetch |
| GP-10 | HTML shell reduction | Keep `index.html` as app mount and asset loader only | HTML contains no business logic or report-builder code |
| GP-11 | Component boundaries | Create owned components for score summary, case table, evidence timeline, and export controls | Components can be tested with DTO fixtures without booting the full app |
| GP-12 | Report snapshot model | Persist immutable report snapshots with builder and redaction versions | Hosted report and export files share the same snapshot content hash |
| GP-13 | Hosted report route | Add `/r/{shareToken}` rendering from report snapshots | A share link opens a redacted report without exposing raw DB ids |
| GP-14 | Export queue | Move JSON/Markdown/CSV/PDF/bundle generation behind an async export job | Export status has queued, running, complete, failed, and expired states |
| GP-15 | Export provenance | Add export metadata for format, creator, input hash, output hash, and redaction policy | Export audit page can prove which snapshot produced each artifact |
| GP-16 | Redaction firewall gate | Run redaction checks before report publish and before export artifact storage | Publish/export is blocked when secret-like or formula-injection payloads are detected |
| GP-17 | A1 contract adapter | Keep accepting A1 `RunResult`, loose `cases[]`, trace events, observations, and agent output | Adapter tests pass using A1 evidence shapes and golden normalized output |
| GP-18 | A2 contract adapter | Keep accepting A2 aggregate grade results and single local judge outputs | Adapter tests preserve score, pass/fail, primary failure class, and judge modes |
| GP-19 | A3 compatibility envelope | Version A3 normalized report DTOs and support older fixtures through an adapter | Old A3 fixtures render without manual conversion |
| GP-20 | Official API-shaped runs | Accept official UI-style `result.tests[].action_results[]` alongside local `cases[]` | Import test maps official run detail into A3 case summaries |
| GP-21 | PostgreSQL migration path | Add SQL migrations for core tables and indexes | CI applies migrations from empty DB and validates rollback or down-migration policy |
| GP-22 | SQLite developer mode | Add SQLite schema compatibility for local demos and tests | Beginner setup can run app with seeded SQLite data and no external service |
| GP-23 | MySQL decision gate | Document whether a customer or platform requires MySQL before supporting it | Architecture decision record names owner, reason, and support burden |
| GP-24 | Tenant and actor model | Add tenant id, actor id, and object ownership to API and DB records | Cross-tenant access tests fail closed |
| GP-25 | Secret handling policy | Block `.env.local`, API keys, cookies, auth headers, and signed URLs from logs and exports | Secret scanner and redaction fixture tests pass in CI |
| GP-26 | Share-link security | Add expiry, revocation, scope, view audit events, and optional password or auth-bound access | Revoked and expired links return controlled errors and no report body |
| GP-27 | Observability baseline | Emit metrics for import, query, report build, export, and share-link view paths | Release evidence includes latency, error rate, and redaction failure counters |
| GP-28 | Verification evidence bundle | Generate a migration evidence bundle for each release candidate | Bundle contains command list, test results, fixture hashes, DB migration version, and report snapshot hashes |
| GP-29 | Backfill plan | Provide a one-time importer for existing sanitized fixtures and generated reports | Backfill dry run reports row counts and skipped duplicates |
| GP-30 | Kill switch and fallback | Keep static fixture mode behind a local-only flag during early migration | API outage test confirms local demo mode works without production secrets |

## A1/A2/A3 Contract Compatibility

Compatibility must be additive. A3 should not require A1 or A2 to change their existing output shapes before the SaaS API can launch.

Required source envelopes:

- A1 `RunResult` root objects with `run_id`, `cases`, `trace_completeness`, and aggregate metrics.
- A1 case-level objects with `case_id`, `scenario_id`, `expected`, `actual`, `observations`, `agent_output`, and optional `grade`.
- A1 trace and observation event streams.
- A2 aggregate grade reports with `grade_results`.
- A2 single local judge outputs with pass/fail, score, primary failure class, and judge details.
- A3 normalized report fixtures and dashboard-ready report objects.
- Official API-shaped run payloads that use `result.tests[]` and action-level result structures.

Compatibility rules:

- Adapters may add fields, but must not remove existing A3 normalized fields without a version bump.
- Score scale must be explicit at adapter boundaries.
- Unknown fields should be preserved in a raw payload hash or raw JSON archive, but not blindly exposed to the frontend.
- Missing optional evidence should produce clear `unavailable` states, not crashes or guessed values.
- The hosted report snapshot should store the adapter version used to build it.

## Secret And Data Safety Requirements

- Never ship API keys, session cookies, auth headers, raw `.env.local` content, or bearer tokens to the browser.
- Never store signed media URLs as durable report content; store storage keys or redacted references and mint short-lived URLs on authorized access.
- Scrub token-like strings from JSON, Markdown, CSV, PDF, logs, screenshots, and hosted report HTML.
- Keep spreadsheet formula injection protections for CSV and tabular exports.
- Do not include raw customer prompts, media, or traces in public share links unless an explicit redaction policy allows them.
- Add audit events for import, report snapshot creation, export creation, share link creation, share link view, revocation, and redaction failure.
- Separate public report tokens from database ids.
- Rotate share tokens on report re-publish when the redaction policy changes.

## Verification Evidence Plan

Each migration stage should produce evidence that can be reviewed without reading secrets.

Minimum evidence bundle:

- Git commit or working tree identifier.
- Migration version and database type used.
- Import command name, source fixture names, row counts, skipped duplicate counts, and payload hashes.
- API contract test results.
- A1/A2/A3 adapter test results.
- Redaction firewall test results.
- Hosted report snapshot id, content hash, redaction policy version, and builder version.
- Export artifact hashes for JSON, Markdown, CSV, PDF, or bundle outputs.
- Screenshot or DOM smoke evidence for run list, case detail, hosted report, and export status pages.
- Audit event samples with ids and timestamps only, no sensitive values.

Suggested local verification commands, to be adjusted once implementation exists:

```text
npm test -- tests/a3
npm run a3:db:migrate -- --database sqlite --dry-run
npm run a3:import -- --source fixtures/a3/p3 --database sqlite --redacted-only
npm run a3:contract:test -- --sources a1,a2,a3,official-api
npm run a3:redaction:test
npm run a3:report:build -- --database sqlite --run-id <seeded-run-id>
npm run a3:export:test -- --formats json,md,csv,pdf
```

Evidence rule:

- Commands may print counts, ids, hashes, schema versions, and pass/fail summaries.
- Commands must not print tokens, cookies, signed URLs, request headers, `.env.local` values, raw account identifiers, or unredacted customer payloads.

## Commercial Readiness Gates

| Gate | Required Before Customer-Visible SaaS |
|---|---|
| Data source gate | DB-backed API is default for run list, case detail, report model, and export queue |
| Contract gate | A1, A2, A3, and official API-shaped payload adapter tests pass |
| Security gate | Secret scanner, redaction firewall, CSV injection checks, and share-link access tests pass |
| Report gate | Hosted report and downloaded export are generated from the same immutable snapshot |
| Operations gate | Import, report build, export job, and share-link view metrics exist |
| Recovery gate | Failed imports and exports are retryable without duplicate report snapshots |
| Evidence gate | Release candidate includes a human-readable evidence bundle |

## Key Risks And Mitigations

| Risk | Mitigation |
|---|---|
| A3 accidentally diverges from A1/A2 evidence semantics | Keep adapter golden tests and explicit schema versions |
| Static fixtures hide DB pagination or tenancy bugs | Move default app path to API and add seeded DB smoke tests |
| Hosted reports leak secrets through exports or media URLs | Block publish/export behind redaction firewall and short-lived signed access |
| Report snapshots become mutable | Store immutable content hash and create new snapshot on rebuild |
| MySQL support increases scope without a buyer | Require a documented decision gate before implementation |
| Beginner local setup becomes too heavy | Keep SQLite seed path and static local fallback during the transition |

## Draft Implementation Backlog

1. Add A3 DB schema ADR covering PostgreSQL, SQLite, and MySQL decision.
2. Define API DTOs and freeze the first versioned contract.
3. Build SQLite seed importer for current sanitized fixtures.
4. Add PostgreSQL migrations for core tables.
5. Add DB-backed run list API.
6. Add DB-backed case detail API.
7. Add trace pagination API.
8. Componentize dashboard views around API DTOs.
9. Add report snapshot persistence.
10. Add hosted report route and share link model.
11. Add export queue with snapshot provenance.
12. Add redaction firewall as a publish/export gate.
13. Add compatibility tests for A1/A2/A3/official API-shaped inputs.
14. Add release evidence bundle generator.
15. Add observability and audit events.

## Open Questions

- Which auth model should A3 use first: existing platform auth, internal service auth, or a temporary local-only token for pilot deployments?
- Should hosted reports support public expiring links, auth-bound links, or both?
- Which export formats are required for the first customer-facing release: JSON, Markdown, CSV, PDF, bundle, or a smaller subset?
- What is the retention policy for raw imported payloads after normalized DB records and report snapshots are created?
- Does any near-term customer or deployment target require MySQL, or can production standardize on PostgreSQL?

## Recommended Next Step

Start with Phase 0 and Phase 1 together: freeze the DTO contract, add API-backed reads over the existing fixture-equivalent data, and create the verification evidence bundle format. That gives the team a controlled path from static local evidence to SaaS behavior without breaking A1/A2/A3 compatibility.
