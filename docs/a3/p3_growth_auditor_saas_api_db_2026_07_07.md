# P3 Growth-Auditor: SaaS API And DB Slice - 2026-07-07

## Commercial Verdict

This round moves A3 closer to a sellable Agent Release Intelligence Platform because it turns the dashboard from a local artifact viewer into the beginning of an API-backed product surface. The new API/store/report slice is still not full SaaS, but it creates the right product direction: durable data source boundary, hosted report payload, redaction gate, and DB-ready contract.

## Newly Sellable Capabilities

- API-backed dashboard payload for run/case/report data.
- DB-ready store boundary that can later swap fixture data for SQL-backed data.
- Shareable hosted report payload with report id, share URL path, content hashes, and redaction status.
- SaaS Runtime dashboard panel that shows whether data is static fixture or API/DB-ready.
- Local API server smoke path for demos and future hosted deployment.
- A3 migration plan with 30 concrete growth points.

## What Is Still Toy-Like

- The API server is local and unauthenticated.
- The store has memory/file/fixture modes, but no SQL adapter yet.
- Hosted reports are payloads, not rendered hosted pages with access control.
- API-backed mode still depends on redacted fixtures until import endpoints exist.
- Team, billing, quota, and permission controls are documented but not implemented.

## Why Customers Would Pay More

- Release managers can see a path from failed run to reportable evidence, not just a local demo.
- Security reviewers get redaction status and content hashes before report sharing.
- Engineering teams get a future-proof integration boundary instead of copying files into a dashboard.
- Enterprise buyers can ask for self-host/DB-backed deployment without forcing a rewrite of the dashboard contract.

## Risk Reduction

- Existing A1/A2 contracts still work through A3 normalization.
- Shareable reports reuse export redaction instead of inventing a second safety path.
- API-backed dashboard mode has tests, so future DB work can preserve the same payload shape.
- `.env.local` and real API keys remain outside committed files.

## Enterprise / Self-Host Readiness

- Recommended production DB: Postgres.
- Local development path: JSON file or SQLite-like future adapter.
- MySQL compatibility: possible through the same store interface if the team chooses it.
- Required enterprise controls still missing: auth, RBAC, tenant scoping, audit event persistence, report access policy, retention policy.

## Next 20 Growth Points

1. Add SQL adapter behind `a3_store.mjs`.
2. Add migration files for `runs`, `cases`, `grade_results`, `trace_events`, `shareable_reports`, and `audit_events`.
3. Add `POST /api/a3/runs/import` for A1 RunResult.
4. Add `POST /api/a3/grades/import` for A2 GradeResult.
5. Add idempotency keys for imports.
6. Add hosted report HTML route.
7. Add share link expiry and revocation.
8. Add audit events for report creation and share views.
9. Add tenant/project scope fields to every API response.
10. Add auth mock shell that can later map to real user/org roles.
11. Add report access policy: private/team/public.
12. Add export job status: queued/running/complete/failed.
13. Add API error/empty/loading states in dashboard.
14. Add API-backed raw A1 source.
15. Add API-backed raw A2 source.
16. Add API-backed P3 official demo source.
17. Add trace-event pagination endpoint.
18. Add media-evidence metadata endpoint without signed URL leakage.
19. Add PR comment link to hosted report.
20. Add CI command that starts A3 API server and runs dashboard API smoke.

## Highest-Money Direction

The most valuable next path is `report export -> shareable hosted report -> PR/release gate evidence`. That path enters the customer's release workflow, gives reviewers something they can sign, and justifies enterprise pricing better than another static visualization.
