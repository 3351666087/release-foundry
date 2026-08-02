# P3 API-Backed Release Evidence - 2026-07-08

## Goal

Move A3 release evidence from a dashboard/report decoration into an API-backed, DB-ready, hosted-report-safe product object.

This follows:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- `static -> API-backed`
- `mock fixture -> real DB data`
- `report export -> shareable hosted report`

## Lane

A3 / Product Console / Review Workflow / Report Center.

## Language And Boundary

- Language/framework: JavaScript ESM on the existing Node test runner.
- Service boundary: `services/report` A3 store, API server, shareable report, Report Center, Artifact Registry, SQL migration contract, SQLite adapter.
- No A1 runner logic was changed.
- No A2 judge semantics were changed.

## What Changed

- Fixture-backed A3 sources now load existing redacted release evidence fixtures at the store boundary.
- `/api/a3/dashboard` now returns a sanitized `release_evidence_summary`.
- Added the data method and API route shape:
  - `GET /api/a3/releases/:releaseId/evidence-summary`
- Shareable hosted reports now include:
  - `release_evidence_summary`
  - `release_evidence_snapshot`
  - a Release Evidence HTML section for active hosted reports
  - no release body on denied pages
- Report Center now records release evidence readiness per hosted report.
- Report Center manifest now includes `release_evidence_summary` as a named artifact.
- Artifact Registry now treats `release_evidence_summary` as a first-class report artifact.
- SQL migration contract now includes `release_evidence_summaries`.
- SQLite store now persists release evidence summary rows from dashboard snapshots.

## A1/A2 Compatibility

A3 still reads A1 data through normalized runs, cases, traces, observations, and tool calls.

A3 still reads A2 data through grade results, score, pass/fail, judge results, and primary failure class.

Release evidence is downstream A3 packaging. It does not rewrite A1 input data or A2 grading output.

## API / DB / Artifact Contract

New or strengthened contract anchors:

- `a3.release_evidence_api_response.v1`
- `a3.release_evidence_api_link.v1`
- `a3.release_evidence_snapshot.v1`
- SQL table: `release_evidence_summaries`
- Artifact type: `release_evidence_summary`
- Manifest artifact id: `release_evidence_summary`

## Tenant / Auth / RBAC / Usage / Audit Implications

- Release evidence API responses include tenant scope metadata.
- Real auth and RBAC are not enforced yet; this remains local/dev API evidence.
- Hosted reports store snapshot hashes so future audit can prove what was shared.
- Raw share tokens are not exposed in stored reads.
- Raw fixture bodies, raw GitHub request bodies, tokens, cookies, secrets, and private keys are not exposed through the release evidence API response.
- SQLite persistence proves the summary can move toward Postgres-backed SaaS storage.

## What This Does Not Claim

- It does not configure live GitHub branch protection.
- It does not prove live GitHub Check or PR comment readback.
- It does not add SSO/OIDC reviewer identity binding.
- It does not replace SQLite with production Postgres.
- It does not call real ReleaseFoundry or GitHub mutation APIs.

## Verification

Focused tests:

```text
node --test tests/a3/a3_store.test.mjs tests/a3/shareable_report.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/report_center_index.test.mjs tests/a3/report_center_manifest_contract.test.mjs tests/a3/artifact_registry.test.mjs
node --test --test-concurrency=1 (rg --files tests/a3 -g "*.test.mjs")
git diff --check
```

Result:

```text
Focused: 20 pass, 0 fail
Full A3 single-threaded: 167 pass, 0 fail
diff --check: no whitespace errors; Windows LF/CRLF warnings only
```

## Next Top 3

1. Add live-shaped GitHub readback fixtures for Check Run and PR comment without using raw tokens.
2. Add Postgres migration/apply smoke once A1 platform DB runner is ready.
3. Add tenant-scope negative tests for release evidence API once hosted auth/RBAC is available.
