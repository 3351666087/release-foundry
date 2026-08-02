# A3 Billing Migration Dashboard Evidence - 2026-07-09

## Scope

This evidence note covers the Playwright-visible A3 dashboard/API proof for Billing Migration Readiness.

## Added Coverage

- `tests/e2e/a3-dashboard-api-backed.spec.ts`
  - Verifies the API-backed dashboard exposes `GET /api/a3/billing/migration-readiness`.
  - Verifies the SaaS Runtime evidence lists `014_billing_migration_readiness`, `billing_migration_readiness`, and `billing_ledger_events`.
  - Calls the local test server route `GET /api/a3/billing/migration-readiness?source=mock`.
  - Asserts the response schema is `a3.billing_migration_readiness.v1`.
  - Asserts the readiness status is `read_only_migration_contract_ready`.
  - Asserts live customer billing is not ready and A3 did not read `.env.local`, call a real API, or call a real payment provider.
  - Asserts the response/body do not expose common token or email patterns.

## Screenshot


The screenshot is generated from the local Playwright static server only. It uses redacted fixtures and local A3 API routes; no real external API, billing provider, token, email, or customer account is captured.

## Verification Results

Focused Playwright command:

```powershell
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts --grep "renders Billing Migration Readiness evidence"
```

Result: failed after the screenshot was captured.

Observed failure:

```text
Access to script at 'node:crypto' from origin 'http://127.0.0.1:4173' has been blocked by CORS policy.
Failed to load resource: net::ERR_FAILED
```

Interpretation: the dashboard shell and `#billing-migration-readiness` panel are visible, and the local API route works, but the current dashboard implementation imports a Node-only `node:crypto` dependency into the browser path before the API-backed dashboard can finish loading.

Focused local API verification:

```powershell
Invoke-WebRequest "http://127.0.0.1:4891/api/a3/billing/migration-readiness?source=mock" -UseBasicParsing -TimeoutSec 20
```

Result:

- HTTP 200
- Schema: `a3.billing_migration_readiness.v1`
- Readiness: `read_only_migration_contract_ready`
- Live billing ready: `false`
- `.env.local` read: `false`
- Real payment provider called: `false`

## Safety Notes

- `.env.local` was not read.
- No real ReleaseFoundry, GitHub, billing provider, hosted auth, email, database, or cloud mutation API was called.
- The dashboard evidence is local and API-backed through `tests/e2e/static-dashboard-server.mjs`.
- A3 remains a read-only consumer of billing migration evidence; A1 still owns durable ledger migrations, provider webhook ingestion, hosted auth/RBAC, and live billing reads.
