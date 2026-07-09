# A3 Live Workflow Readiness - 2026-07-09

This round turns the team lead's next six SaaS items into one A3 dashboard/API
contract:

1. GitHub PR check live publishing
2. PR comment live publishing
3. reviewer approve / deny / waiver workflow
4. dashboard-visible human operation records
5. billing/admin reads real usage and billing readiness state
6. report share links can expire, be revoked, and leave audit evidence

## What Changed

- Added `services/report/a3_live_workflow_readiness.mjs`.
- Added `a3.live_workflow_readiness.v1`.
- Added `GET /api/a3/live-workflow/readiness`.
- Added `live_workflow_readiness` to API-backed dashboard payloads.
- Added dashboard panel `#live-workflow-readiness`.
- Added navigation entries for Live Workflow.
- Added tests:
  - `tests/a3/a3_live_workflow_readiness.test.mjs`
  - updated `tests/a3/a3_api_server.test.mjs`
  - updated `tests/a3/dashboard_wiring.test.mjs`

## Current Truth

A3 now has a single read model that can say which of the six commercial
workflow items are locally modeled and which still need real hosted
infrastructure.

The current state is intentionally conservative:

- GitHub Check and PR Comment publishers exist, but live use still needs a
  maintainer-approved GitHub Action/App token and sanitized readback capture.
- Reviewer approval, denial, and waiver records are supported by the A3 API and
  event outbox.
- Human operation records are visible through reviewer workflow and SaaS admin
  request records.
- Usage and billing readiness are read-only; billing mutations remain disabled.
- Hosted report links are revocable, expirable, and audit-recorded.

## A1/A2 Boundary

A3 only reads downstream evidence:

- A1 remains owner of runner, auth, API gateway, usage ledger, billing provider,
  quota enforcement, and GitHub/CI integration boundaries.
- A2 remains owner of judge semantics, score/pass/fail, release policy, failure
  taxonomy, and security verification.
- A3 turns A1/A2 outputs into dashboard, report, review, usage, billing,
  audit, and hosted-report evidence without changing their source semantics.

## Safety

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub API call was made.
- No billing provider call was made.
- No key, token, cookie, email, signed URL, account value, or payment secret was
  added to docs, fixtures, or code.
- The new readiness object reports local state and future live requirements; it
  does not perform live external mutations.

## Verification

```text
node --test tests\a3\a3_live_workflow_readiness.test.mjs tests\a3\a3_api_server.test.mjs tests\a3\dashboard_wiring.test.mjs tests\a3\a3_peer_branch_calibration.test.mjs tests\a3\a3_tenant_event_source_artifact_contract.test.mjs
```

Result:

```text
45 passed, 0 failed
```

Final validation also passed:

```text
node --test tests\a3\*.mjs
npm.cmd run test:e2e
python scripts\cl_guard.py commercial
python scripts\cl_guard.py hygiene
git diff --check
git check-ignore -v .env.local node_modules docs\screenshots\playwright-results
```

Results:

- Full A3 Node suite: 249 passed, 0 failed.
- Playwright E2E: 9 passed, 0 failed.
- Commercial CL: passed with 0 blockers and 0 advisories.
- Hygiene CL: passed with no findings.
- Whitespace check: passed.
- Secret/large artifact ignore check: passed for `.env.local`, `node_modules`,
  and Playwright result artifacts.

## Next Best Steps

1. Run live GitHub Check and PR Comment publishing from a maintainer-approved
   GitHub Action/App, then capture sanitized readback receipts.
2. Persist live workflow readiness in Postgres/RLS once A1 auth and storage
   boundaries are available.
3. Extend dashboard human-operation records with actor-hash, event id, status,
   and reviewer role filters.
