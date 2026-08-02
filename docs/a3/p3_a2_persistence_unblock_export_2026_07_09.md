# A3 A2 Persistence / Unblock Export Growth - 2026-07-09

## Lane

A3 / Product Console / Report Center / Release Review Workflow.

## Why this matters commercially

A2 now emits two release-grade artifacts that A3 should not ignore:

- `fixtures/a2/results/a2_result_persistence_manifest.json`
- `fixtures/a2/results/a2_release_unblock_checklist.json`

These artifacts answer two buyer questions:

- Did the judge and release-gate result become durable audit evidence?
- If a release is blocked, what exact evidence and reviewer work unblocks it?

That is directly tied to paid enterprise value: fewer risky agent releases, stronger audit exports, and clearer reviewer sign-off.

## What changed

- Added `summarizeA2ResultPersistence` to `services/report/report_builder.mjs`.
- Added `summarizeA2ReleaseUnblockChecklist` to `services/report/report_builder.mjs`.
- Extended the existing A2 readiness bundle so A3 exports can carry:
  - `resultPersistence`
  - `resultPersistenceManifest`
  - `releaseUnblockChecklist`
- Added `a2_result_persistence` and `a2_release_unblock_checklist` to JSON report export.
- Added `A2 Result Persistence` and `A2 Release Unblock Checklist` sections to Markdown report export.
- Wired dashboard export loading for:
  - `a2_result_persistence_manifest.json`
  - `a2_release_unblock_checklist.json`
- Added report builder and dashboard wiring tests.

## API / DB / Event / Artifact Contract

- API: no new public API route in this round.
- DB: no new table in this round; this is export-level consumption of A2 evidence.
- Event: no new emitted event in this round.
- Artifact: A3 report export now treats A2 persistence and unblock checklist as report artifacts that can be included in audit bundles later.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: result persistence summary preserves `tenant_id`, `project`, `run`, and `dataset_id` from A2.
- Auth/RBAC: no hosted auth or role mutation added.
- Usage: no billing event added yet; future usage meters should count `a2_persistence_records_exported` and `release_unblock_checklists_exported`.
- Audit: stronger. A3 exports can now show durable A2 judge records, release gate record count, scenario selection record count, and unblock owner roles.
- Redaction: raw private evidence is not read. A2 private refs remain named anchors only.

## A1 / A2 Calibration

- A1: unchanged. A3 still consumes A1 run/trace evidence separately.
- A2: newly consumed fields come from A2-owned fixtures and schemas:
  - `docs/a2/schemas/result_persistence_manifest.schema.json`
  - `docs/a2/schemas/release_unblock_checklist.schema.json`
- A3 does not change A2 judge semantics. It only summarizes A2 outputs for report/export/review consumption.

## Verification

```text
node --check services/report/report_builder.mjs
node --check apps/dashboard/src/app.mjs
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

## Next Growth

1. Persist these A2 export summaries into A3 artifact registry entries.
2. Add a dashboard panel for release unblock checklist next actions.
3. Add usage meters for exported A2 persistence and unblock evidence.
4. Hash these summaries into audit bundle reseal inputs.
5. Add reviewer workflow actions that map C3/C4/C5 unblock tasks to owner lanes.
