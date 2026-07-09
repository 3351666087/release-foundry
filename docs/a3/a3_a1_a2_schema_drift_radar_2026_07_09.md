# A3 A1/A2 Schema Drift Radar - 2026-07-09

## Purpose

This round adds an executable A3-side drift radar for the A1/A2 schemas that
A3 consumes. The goal is to catch upstream contract changes before they silently
break dashboard triage, report export, release gates, review workflow, usage
meters, or audit artifacts.

This is a consumer-side guard only. It does not change A1 runner semantics or
A2 judge semantics.

## New Code

- `services/report/a3_schema_drift_radar.mjs`
- `tests/a3/a3_schema_drift_radar.test.mjs`

The radar reads A1/A2 schema files, computes SHA-256 hashes, and checks the
critical fields A3 depends on.

This round also extends the downstream A3 consumers that depend on those
schemas:

- `services/report/report_builder.mjs` preserves newer G3 evidence-readiness
  fields for A1 official API readonly manifests, mutating API indexes, and paid
  media summaries.
- `services/report/report_builder.mjs` preserves newer A2 persistence fields
  for `release_unblock_checklist` and `a1_ingestion_digest` records.
- `services/report/a3_source_artifacts.mjs` hashes optional A1/A2 calibration
  inputs as metadata-only source artifacts when those inputs are present.

## New API Surface

- `GET /api/a3/a1-a2/schema-drift`

The route is protected by the A3 RBAC boundary:

- operation: `read_schema_drift`
- required permission: `audit:read`
- allowed local roles: owner, admin, reviewer, auditor

Viewers are denied with `a3.api_authz_denied.v1`.

## Covered A1 Schemas

- `docs/a1/schemas/run_result.schema.json`
- `docs/a1/schemas/case_result.schema.json`
- `docs/a1/schemas/trace_event.schema.json`
- `docs/a1/schemas/observation.schema.json`

A3 checks fields used by run list, case detail, trace timeline, tool-call diff,
incident replay, release evidence, usage ledger, and report export.

## Covered A2 Schemas

- `docs/a2/schemas/grade_results.schema.json`
- `docs/a2/schemas/release_gate.schema.json`
- `docs/a2/schemas/result_persistence_manifest.schema.json`
- `docs/a2/schemas/release_unblock_checklist.schema.json`

A3 checks fields used by failure clusters, release war room, reviewer workflow,
GitHub PR gate, artifact registry, audit export, and report export.

## Remote Branch Observation

After `git fetch origin`, A3 observed:

- `origin/codex/a1-local-sdk-runner` has newer A1 work around route scope,
  quota, mutating API evidence, durable Postgres API keys, and SaaS migration
  manifests.
- `origin/dev/g3-a2-calibration` has newer A2 work around cross-lane security,
  scenario generation backlog, SQL store report, and paid media evidence
  context.

This round does not merge those branches. The radar validates the current
main-aligned schema files and gives A3 an executable place to extend checks when
those A1/A2 branches are merged.

A3 also inspected the newer remote A2 schema shapes for:

- `a1_official_api_readonly_manifest`
- `a1_official_api_mutating_index`
- `a1_official_api_paid_media_summary`
- `release_unblock_checklist` result-persistence records
- `a1_ingestion_digest` result-persistence records
- cross-lane security context
- SQL store reports

Only the fields that directly affect A3 report/export/source-artifact behavior
were implemented in this round. Cross-lane security and SQL store reports remain
next-step dashboard/report consumers.

## Safety

The radar is hash-only and metadata-only:

- no raw schema payload is embedded in the API response
- no `.env.local` or key material is read
- no API key, token, cookie, email, signed URL, or private evidence is written

## Validation

Focused validation:

```text
node --check services/report/report_builder.mjs
node --check services/report/a3_source_artifacts.mjs
node --check services/report/a3_schema_drift_radar.mjs
node --test tests/a3/report_builder.test.mjs tests/a3/a3_tenant_event_source_artifact_contract.test.mjs tests/a3/a3_schema_drift_radar.test.mjs tests/a3/a3_auth_rbac_boundary.test.mjs tests/a3/a3_api_server.test.mjs
```

Result:

```text
Focused: 59 tests passed, 0 failed
Full A3: 241 tests passed, 0 failed
E2E: 9 tests passed, 0 failed
commercial CL guard: passed
hygiene CL guard: passed
git diff --check: passed
```

## Next Growth Points

1. Extend radar after A1 route scope and quota schemas land in main.
2. Extend radar after A2 cross-lane security and SQL store schemas land in main.
3. Add dashboard visibility for schema drift status.
4. Add report/export drift summary.
5. Add artifact registry entries for drift radar snapshots.
6. Persist drift radar snapshots in Postgres/SQLite once production DB wiring is
   ready.
7. Link drift changes to bundle reseal impact.
8. Add CI guard mode so schema drift blocks risky A3 changes.
9. Add A3 summaries for A2 cross-lane security context.
10. Add A3 summaries for A2 SQL store reports once A2's DB persistence shape is
    merged into main.
