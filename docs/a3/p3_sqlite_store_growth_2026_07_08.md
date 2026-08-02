# A3 SQLite Store Growth Pass

Date: 2026-07-08

## Goal

Move A3 one step away from fixture-only storage and toward a real SaaS persistence layer.

This pass implements the first local SQL-backed store target using Node's built-in SQLite runtime. It does not replace the Postgres/MySQL migration contract. It gives the student team a working DB-backed MVP path before a production database choice is finalized.

## What changed

- Added `services/report/a3_sqlite_store.mjs`.
- Added `tests/a3/a3_sqlite_store.test.mjs`.
- Wired the dashboard Report Center to revoke hosted reports through the existing A3 API.
- Added dashboard wiring coverage for hosted report revocation and report evidence refresh.

## Commercial value

A3 can now show a buyer-facing story that is stronger than "we have mock JSON":

1. A1 RunResult imports can land in a SQL-backed store.
2. A2 GradeResult imports can land in a SQL-backed store.
3. Idempotency receipts become inspectable DB rows.
4. Hosted reports become inspectable DB rows.
5. Share links are stored by hash, not raw token.
6. View events and revocations become audit rows.
7. Usage ledger rows become inspectable billing evidence.
8. The same API server can run against the SQLite store without changing routes.

## Safety boundary

- No `.env.local` was read.
- No ReleaseFoundry API key was printed or stored.
- No real ReleaseFoundry, GitHub, billing, auth, team, or cloud mutation API was called.
- The SQLite store records redacted state and hashed share-link values only.
- Missing share-token access is stored as an audit event without creating fake report rows.

## Growth points for the next round

### PR Gate

1. Persist GitHub check request/response metadata in SQL.
2. Add marker-based PR comment updates tied to report ids and audit bundle ids.

### Production Replay

3. Add `replay_jobs` table contract and local job records.
4. Connect Incident Replay Queue items to replay job receipts.

### Enterprise Audit

5. Persist waiver and approval records in SQL.
6. Add signed archive or zip verifier for audit bundles.

### Self-Host

7. Add a local `docker-compose` target with A3 API plus SQLite file mount.
8. Add migration apply/verify CLI for SQLite.

### Trace Ingestion

9. Add batch trace-event import route.
10. Persist trace event summaries and tool-call rows from A1 payloads.

### Judge Calibration

11. Persist A2 judge version/policy metadata beside grade results.
12. Add reviewer override rows that can feed calibration.

### Incident Report

13. Generate customer-safe incident reports from failed cases.
14. Link incident report exports to Artifact Registry entries.

### Review Workflow

15. Add reviewer assignment state to SQL.
16. Add reviewer comments and SLA timestamps.

### Billing / Usage

17. Make usage ledger append-only instead of refresh-derived.
18. Add quota preview rows for soft/hard limit state.

### API Platform

19. Add tenant-scoped source reads to every report API route.
20. Add OpenAPI contract for A3 API-backed dashboard routes.

### Product UX

21. Add Report Center detail drawer with manifest and view-audit rows.
22. Add hosted report lifecycle filters: active, expired, revoked, blocked.

## Verification

```text
node --test tests/a3/a3_sqlite_store.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs
```

Result:

```text
38 tests
38 pass
0 fail
```

Syntax check:

```text
node --check apps/dashboard/src/app.mjs
node --check apps/dashboard/src/api-client.mjs
node --check services/report/a3_sqlite_store.mjs
```

Result: passed.

## Current interpretation

This is not yet production Postgres, auth, RBAC, billing, or object storage. It is the first working SQL-backed A3 store that proves A3 can move from static fixture evidence to a real persistence boundary while preserving A1/A2 compatibility and hosted report lifecycle behavior.
