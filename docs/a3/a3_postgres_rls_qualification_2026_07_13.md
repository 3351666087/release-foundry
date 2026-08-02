# A3 PostgreSQL RLS Qualification

- Date: 2026-07-13
- Owner: A3 Deployment Operations with A1 data-plane contracts
- Database: PostgreSQL 17.9
- Evidence level: `sandbox_verified`
- Target customer environment verified: `false`
- Production readiness changed: `false`

## 1. Beginner Summary

The previous A3 round proved that A1 health, worker recovery, dead-letter handling, and local
object integrity execute correctly. The durable A3 reference store was still SQLite, so the
project had not executed the A3 migration 019-to-020 upgrade chain on PostgreSQL.

This round runs a real PostgreSQL server and asks four concrete questions:

1. Can migration 019 followed by RLS hardening migration 020 run twice without breaking?
2. Can a correctly scoped tenant read and write its own row?
3. Can the same role read or write another tenant's row?
4. What happens when no tenant scope is supplied?

The answer is now executable and verified: same-scope access succeeds, cross-scope reads
return zero rows, cross-scope writes are rejected by PostgreSQL RLS, and missing scope also
returns zero rows.

## 2. Real Execution Result

| Check | Result | Meaning |
|---|---:|---|
| PostgreSQL server | 17.9 | A real PostgreSQL engine executed the SQL |
| Migration 019-to-020 chain apply count | 2 | Both create and upgrade migrations are idempotent |
| RLS enabled | true | Row-level security is active |
| RLS forced | true | Table owners cannot silently bypass the policy |
| Runtime role | NOSUPERUSER + NOBYPASSRLS | The test role cannot evade RLS |
| Five scope levels | 5/5 | organization, tenant, workspace, project, environment |
| Same-scope read | 1 row | Allowed tenant data is visible |
| Same-scope write | allowed | Allowed tenant data can be inserted |
| Cross-scope read | 0 rows | Other tenant data is invisible |
| Cross-scope write | denied | PostgreSQL rejects the write |
| Missing-scope read | 0 rows | Missing context fails closed |
| Probe cleanup | complete | Test rows and temporary role were removed |

The sanitized receipt is:

```text
fixtures/a3/p3/a3_postgres_rls_qualification_20260713.redacted.json
```

It contains PostgreSQL version, migration hash, policy state, counts, booleans, and authority
boundaries. It does not contain a DSN, host, username, password, SQL output, local path, or
customer data.

## 3. Migration 019-to-020 Upgrade

Published migration `019_self_host_sandbox_calibrations` remains unchanged and creates the
base table. New migration `020_self_host_sandbox_scope_hardening` upgrades existing and fresh
databases with:

- a composite primary key across all five scope columns plus calibration id;
- a scope-first digest uniqueness index;
- `ENABLE ROW LEVEL SECURITY`;
- `FORCE ROW LEVEL SECURITY`;
- one `USING` and `WITH CHECK` policy requiring exact values for:
  - `app.a3_organization_id`
  - `app.a3_tenant_id`
  - `app.a3_workspace_id`
  - `app.a3_project_id`
  - `app.a3_environment_id`

Missing settings evaluate to no match. A client cannot omit scope and accidentally receive
all rows.

SQLite does not receive PostgreSQL policy syntax. It remains a local reference store and is
not presented as RLS evidence.

## 4. Probe Architecture

```text
Target PostgreSQL
  -> migration 019 + 020 chain apply #1
  -> migration 019 + 020 chain apply #2
  -> create temporary NOSUPERUSER / NOBYPASSRLS role
  -> seed scope A and scope B rows
  -> same-scope read and write
  -> cross-scope read and denied write
  -> missing-scope read
  -> policy/catalog readback
  -> delete probe rows and drop probe role
  -> sanitized qualification receipt
  -> attach to A1 self-host calibration
  -> A3 Store / SQLite payload / API / Delivery UI
```

Implementation:

- `services/report/a3_postgres_rls_probe.mjs`
- `services/report/a3_postgres_rls_probe_cli.mjs`
- `services/report/a3_sql_migrations.mjs`
- `services/report/a3_self_host_sandbox.mjs`
- `apps/webapp/components/self-host-sandbox-panel.tsx`

## 5. Credential and Process Safety

- `psql` runs without a shell.
- Passwords are accepted only through process environment variables.
- CLI arguments intentionally do not support `--password` or `--dsn`.
- The child environment is allowlisted.
- Runtime output has a timeout and byte limit.
- Public output stores no host, DSN, credentials, raw SQL, local path, or account identity.
- PostgreSQL stderr is reduced to a safe error class.
- Cleanup is mandatory; a successful public receipt requires `cleanup_completed=true`.
- A failed phase never changes Deployment Acceptance or A2 authority.

## 6. Product UI

The existing protected endpoint remains:

```text
GET /api/a3/deployment/sandbox-calibration
```

Its response now optionally includes `postgres_qualification`. The Delivery page displays:

- PostgreSQL version;
- migration id and two idempotent applies;
- `ENABLED + FORCED` RLS state;
- cross-tenant write denial;
- cross-tenant and missing-scope zero-row results;
- a visible `sandbox only` boundary.

Screenshots:

- `docs/screenshots/a3-self-host-sandbox-calibration-mobile-390x844-20260713.png`
- `docs/screenshots/a3-postgres-rls-qualification-mobile-390x844-20260713.png`

## 7. What This Does Not Prove

This qualification used an isolated local PostgreSQL process. It does not prove:

- the customer's PostgreSQL identity or network path;
- migration 019-to-020 upgrade in staging or a customer VPC;
- TLS/KMS configuration;
- backup, point-in-time recovery, or restore;
- multi-instance API behavior;
- production object storage or durable queue custody;
- upgrade and rollback;
- a same-candidate A2 Trusted Spine.

Therefore the authoritative posture stays:

```text
Golden Path: 7/11
Deployment Acceptance: 8/17
Current authority: integrity_invalid
Current A2 decision: unknown
Historical A2 decision: block
Production verified receipts: 0
Production ready: false
```

## 8. Verification

Completed checks include:

```text
node --test tests/a3/a3_postgres_rls_probe.test.mjs
node --test tests/a3/a3_self_host_sandbox.test.mjs
node --test tests/a3/a3_self_host_sandbox_integration.test.mjs
node --test tests/a3/a3_commercial_openapi_contract.test.mjs
npm.cmd run check --prefix apps/webapp
cmd /c npx playwright test
```

The real CLI execution produced `postgres_rls_verified`, then an independent database query
confirmed zero remaining probe rows and no remaining probe role.

Final regression passed A3 Node `463` runnable tests plus one explicit live opt-in skip,
A2 `186/186` plus `1050` subtests, A3 Python `2/2`, Next.js typecheck/build with 15 static
pages, and Playwright `40/40`. OpenAPI parity stayed `58/58`; both CL guards, both production
npm audits, export safety, and all sealed rc.2 verifiers passed.

The final remote calibration kept authoritative `main` at `ccf6ce5` and A1 development at `2307231`.
A2 development advanced to `b778e11` with additive multimodal and composite-agent receipt
contracts. Those contracts do not change GradeResult, Decision Ledger, or Trusted Spine, so
they were reviewed as non-main compatibility evidence and were not promoted into A3 authority.

## 9. Next Production Step

Run the same CLI against an authorized staging/VPC PostgreSQL service account, then attach:

1. deployment identity and target-environment alias;
2. migration transaction and rollback receipt;
3. TLS/KMS posture;
4. backup/restore marker;
5. same-tenant allow and cross-tenant deny readback from the deployed API identity.

Only a server-authoritative target receipt may enter the Deployment Receipt verifier. The
local receipt in this document cannot raise `8/17`.
