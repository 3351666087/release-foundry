# A3 Self-host Sandbox Calibration

- Date: 2026-07-13
- Owner: A3 Product / Deployment Operations
- Runtime source: A1 local control plane, worker lifecycle, and object storage
- Evidence level: `sandbox_verified`
- Production verification: `false`

## 1. Beginner Summary

This round answers a narrow but important question:

> Can the code that A1 already built actually run locally, or is A3 only showing a plan?

A3 now starts a constrained Python child process and executes four real A1 behaviors:

1. call the A1 local `/healthz` behavior;
2. enqueue, lease, heartbeat, retry, and dead-letter a worker job;
3. recover a job after its worker lease expires;
4. write an object, read it back, then tamper with it and confirm that the checksum fails.

All four A1 checks pass. A linked PostgreSQL 17.9 qualification also proves the migration 019-to-020 chain
and five-level RLS locally. This still does not prove a customer VPC, signed container,
production networking, backup/restore, or upgrade/rollback.

## 2. What Is Actually Proven

| Check | Result | Evidence class | Production proof |
|---|---|---|---|
| A1 control-plane health | HTTP 200, `status=ok`, `local_only=true` | sandbox verified | No |
| Worker retry/dead-letter | `queued -> leased -> retrying -> dead_lettered` | sandbox verified | No |
| Expired lease recovery | a second worker acquires the expired lease on attempt 2 | sandbox verified | No |
| Local object integrity | write/readback passes and tampering produces SHA/size mismatch | sandbox verified | No |

The public fixture is:

```text
fixtures/a3/p3/a3_self_host_sandbox_calibration_20260713.redacted.json
```

It contains statuses, counts, aliases, contract names, and SHA-256 only. It does not contain
the temporary object path, raw object bytes, credentials, API keys, cookies, emails, signed
URLs, or account data.

## 3. What Is Not Proven

The following checks remain `not_run`:

| Production gap | Why | Required next evidence |
|---|---|---|
| PostgreSQL/RLS isolation | local PostgreSQL passed; target customer environment is not verified | deployed same-tenant allow and cross-tenant deny receipt |
| Container image identity | Docker and Podman are unavailable | signed image digest and runtime readback |
| VPC network policy | a local process cannot represent customer networking | ingress/egress and workload-identity receipt |
| Upgrade/rollback/recovery | no authorized production-like install exists | upgrade, forced failure, rollback, recovery receipt |
| A2 production authority | A3 does not create an A2 Decision Ledger record | same-candidate A2 Trusted Spine |

Therefore the authoritative posture remains:

```text
Golden Path: 7/11
Deployment Acceptance: 8/17
Current authority: integrity_invalid
Current A2 decision: unknown
Historical A2 decision: block
Production verified receipts: 0
Production ready: false
```

## 4. Execution Architecture

```text
A3 CLI
  -> allowlisted environment + timeout + stdout limit
  -> Python A1 probe
  -> A1 health / worker / storage code
  -> JSON schema + secret/path scan
  -> SHA-256-bound redacted calibration
  -> live PostgreSQL 17.9 migration/RLS qualification
  -> Store / SQLite migration 019
  -> deployment:read API
  -> Next.js Delivery operations UI
```

Files:

- `services/report/a3_a1_sandbox_probe.py`
- `services/report/a3_self_host_sandbox.mjs`
- `services/report/a3_self_host_sandbox_cli.mjs`
- `services/report/a3_store.mjs`
- `services/report/a3_sqlite_store.mjs`
- `services/report/a3_sql_migrations.mjs`
- `apps/webapp/components/self-host-sandbox-panel.tsx`
- `apps/webapp/components/pages/delivery-page.tsx`

## 5. API, DB, RBAC, and Audit

API:

```text
GET /api/a3/deployment/sandbox-calibration
```

- Permission: `deployment:read`
- Scope: organization, tenant, workspace, project, and environment
- Hosted identity source: A1 server-verified principal
- Hosted read audit: `route_access.allowed` / `route_access.denied`
- Event outbox: metadata-only access event

Migration `019_self_host_sandbox_calibrations` stores the validated calibration separately
from `deployment_receipts`. Its three authority columns are fixed to false:

- `production_verified`
- `deployment_acceptance_mutated`
- `a2_decision_recomputed`

This separation is intentional. A sandbox success cannot enter the authoritative production
receipt resolver or raise Deployment Acceptance.

## 6. UI States

The Delivery page has Chinese-first and English views for:

- loading;
- ready;
- partial check failure;
- empty/no calibration;
- failed service read;
- denied `deployment:read`;
- safe retry.

It also shows PostgreSQL version, migration 019-to-020 idempotency, forced RLS, same-tenant allow,
cross-tenant denial, missing-scope zero rows, and an explicit local-only boundary.

The primary message is:

```text
Sandbox 4/4 does not change Deployment Acceptance 8/17.
```

Screenshots:

- `docs/screenshots/a3-self-host-sandbox-calibration-desktop-20260713.png`
- `docs/screenshots/a3-self-host-sandbox-calibration-mobile-390x844-20260713.png`
- `docs/screenshots/a3-postgres-rls-qualification-mobile-390x844-20260713.png`

## 7. Security Boundaries

- The child process receives an allowlisted environment, not the parent secret environment.
- Python is invoked without a shell.
- Runtime is bounded by timeout and output-size limits.
- Invalid JSON, wrong schema, missing checks, production overclaims, and A2 overclaims fail closed.
- Token, email, signed URL, cookie, API-key-like value, and absolute-path scans run before acceptance.
- `.env.local` and Ashr API are not used.
- No A1 Runner or A2 Judge semantics are changed.
- The sealed rc.2 bundle, archive, and Release Artifact are not rewritten.

## 8. Verification

Focused verification completed:

```text
python -B -m pytest tests/a3/test_a3_a1_sandbox_probe.py -q -p no:cacheprovider
node --test tests/a3/a3_self_host_sandbox.test.mjs
node --test tests/a3/a3_self_host_sandbox_integration.test.mjs
node --test tests/a3/a3_commercial_openapi_contract.test.mjs
npm.cmd run typecheck
npm.cmd run build
cmd /c npx playwright test tests/e2e/a3-webapp-product-routes.spec.ts --grep "self-host sandbox"
```

The focused Python, Node, TypeScript, production build, and two Playwright workflows pass.
Final local regression also passed A3 Node `458/458`, current-main A2 `186/186` plus
`1050` subtests, Next.js typecheck/build with 15 static pages, and Playwright `40/40`.
Both CL guards passed, both production npm audits found 0 vulnerabilities, and all sealed
rc.2 verifiers passed without rewriting their inputs. Remote CI results are recorded in
`docs/a3/worklog.md` after publish.

## 9. Commercial Meaning

This improves the self-host sales story from "we have a scaffold" to "we can execute and
display a bounded local operations receipt." It is useful in a technical evaluation because
the buyer can see worker recovery and data-integrity behavior. It is not yet a production
installation, so it cannot support a production-ready claim or customer sign-off.
