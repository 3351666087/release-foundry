# A3 Billing Migration Report Artifact - 2026-07-09

ANCHOR: A3_BILLING_MIGRATION_REPORT_ARTIFACT

## Scope

This change wires `a3.billing_migration_readiness.v1` into A3 report export and
Artifact Registry evidence without changing A1 or A2 semantics.

## Report Export

JSON report export now emits `billing_migration_readiness` as a redacted summary
only. The export includes:

- contract id, hash prefix, status, and upstream commit count
- A1-owned DB table names and function names
- replay counts, replay statuses, and usage units
- read-only API, event, artifact, tenant, RBAC, usage, and audit boundaries
- explicit safety booleans for no `.env.local`, no real API, no payment
  provider call, no A3 billing mutation, and no raw provider/customer payload

Markdown report export now includes a human-readable `Billing Migration
Readiness` section with customer value, missing controls, self-host value, and
audit value.

## Artifact Registry

Artifact Registry now registers `billing_migration_readiness` as a control-plane
artifact with:

- `billable_meter`: `billing_readiness_artifacts`
- customer value: safe buyer review of billing ledger migration readiness
- billable value: invoice-preview and usage-unit readiness with A3 writes
  disabled
- self-host value: A1-owned Postgres billing ledger, RLS, and replay contract
  evidence
- audit value: provider-event hashes, replay statuses, tenant/RBAC boundaries,
  and no-raw-payload controls
- missing controls: A1 authenticated billing ledger read API, hosted auth/RBAC,
  A1 provider webhook executor, and live billing readback receipts

The artifact is included in `security_audit_packet` and the new
`billing_migration_packet`.

## Safety

The report and registry consumers summarize only public-safe fields from the
redacted fixture. They do not read `.env.local`, call the ReleaseFoundry API, run a live DB
migration, call a billing provider, or enable billing mutations.

Tests inject fake provider secrets, bearer headers, local paths, and email-like
values into ignored fields to prove those values are not emitted.

## Verification

Expected focused checks:

```bash
node --check services/report/report_builder.mjs
node --check services/report/a3_artifact_registry.mjs
node --test tests/a3/report_builder.test.mjs tests/a3/artifact_registry.test.mjs
```

## Remaining Gaps

A3 still cannot claim live billing. The missing production controls remain
A1-owned authenticated billing ledger read APIs, hosted auth/RBAC enforcement,
A1 provider webhook execution, and live billing readback receipts.
