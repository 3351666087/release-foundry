# A3 Slim Operating Index - 2026-07-09

This file is the short working-memory index for the next A3 rounds.
It does not delete or replace the long worklogs. It tells future Codex runs what
is already done, what is still missing, and which files to read first so the
agent does not waste time rereading every historical growth report.

## Current Snapshot

- Branch: `codex/a3-commercial-growth-round4`.
- Current PR: #28, already pushed in previous round.
- Latest pushed commit before this cleanup: `d21c5b4 Add A3 auth RBAC boundary contract`.
- A3 file surface is large: about 200 A3/service/dashboard/test/e2e files.
- Long history files are evidence archives, not first-read files:
  - `docs/a3/worklog.md`
  - `docs/a3/p3_worklog.md`
  - `docs/a3/acceptance_checklist.md`
  - older `docs/a3/p3_growth_auditor_*.md`

## Read First Next Time

Read these before doing new A3 work:

1. `docs/a3/a3_slim_operating_index_2026_07_09.md`
2. `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
3. `git status -sb`
4. `docs/a3/acceptance_checklist.md` tail only
5. `docs/a3/worklog.md` tail only
6. `services/report/a3_api_server.mjs`
7. `services/report/a3_store.mjs`
8. `services/report/report_builder.mjs`
9. `apps/dashboard/src/app.mjs`
10. The focused tests for the file being changed

Avoid full rereads of old growth-auditor docs unless a failing test or user
request points to one specific artifact.

## Done Enough

These are already good enough for the student MVP and should not be rebuilt
from scratch:

- Run list, case detail, trace timeline, expected-vs-actual, failure clusters.
- Tool-call diff, judge-mode filtering, media metadata, and release triage.
- A3 mock fixture generation from A1/A2-shaped data.
- Local API-backed A3 server and store:
  - dashboard
  - runs/cases
  - report sharing
  - report center
  - artifact registry
  - release evidence
  - admin console
  - review workflow
  - usage/billing readiness
- SQLite-backed local persistence contract.
- Shareable hosted reports with redaction, expiry, revoke, denied pages, and
  view audit.
- Release gate, release war room, incident replay, regression factory, reviewer
  workflow, waiver validation, approval validation.
- GitHub Check / PR comment dry-run publish evidence and readback-shaped
  contracts.
- Audit bundle index and signed audit archive manifest.
- SaaS Admin shell for login, team, API keys, usage, trust, and cloud management
  as safe plan-only or read-only product surfaces.
- Billing and usage preview as read-only, non-payment functionality.
- A1/A2 source artifact hashes for RunResult, Trace, ToolCall, GradeResult, and
  ReleaseGate.
- Commercial OpenAPI contract and Auth/RBAC metadata boundary.
- Playwright TS E2E coverage for dashboard/admin/review/report flows.
- CL guard commercial and hygiene checks.

## Still Missing

These are real gaps, not misunderstandings:

- `ashr.event_envelope.v1` exists but is not uniformly attached to every
  mutation-like receipt and durable audit/event outbox path.
- Idempotency is strong for A1/A2 imports and release readbacks, but not yet
  uniform across share, revoke, admin action, waiver, and approval writes.
- Auth/RBAC is a metadata boundary, not live enforcement. A1 must provide hosted
  auth middleware before A3 can claim production auth.
- Real Postgres/RLS is not implemented. SQLite is a local development contract,
  not production multi-tenant storage.
- Real billing checkout, portal, invoices, quotas, and payment provider webhooks
  are intentionally disabled.
- Live GitHub Check/PR comment/branch-protection enforcement needs maintainer
  approval and real integration.
- Reviewer approval identity binding is hash-sealed/local, not real SSO/OIDC or
  cryptographic production sign-off.
- Signed media URL rendering remains metadata-only until image/audio/video
  access behavior is confirmed.
- Full object storage custody, immutable artifact storage, and production
  bundle reseal gate remain future work.
- A1/A2 schema drift tests should be stronger and closer to
  `docs/a1/schemas` and `docs/a2/schemas`.
- The dashboard is split into webapp-style modules, but the product is not yet a
  full Next.js/React/Tailwind SaaS app.

## Do Not Spend Time On

- Do not rewrite A1 runner, SDK, trace, tool-call, auth, usage, or artifact
  semantics from A3.
- Do not rewrite A2 judge, score, pass/fail, release policy, or failure taxonomy.
- Do not re-crawl official Ashr pages unless there is a specific new question.
- Do not create real billing, real team invites, real API-key rotation, real
  Trust publish, or live cloud mutations from A3.
- Do not add more growth-auditor reports unless they produce an executable
  contract, test, fixture, or route.
- Do not keep opening subagents for broad analysis. Use at most two focused
  subagents only when their work is independent, and close them when done.
- Do not read or print `.env.local`, API keys, cookies, tokens, raw share
  tokens, emails, signed URLs, or payment secrets.

## Next Best Work

The next high-value A3 sequence is:

1. Attach `ashr.event_envelope.v1` to mutation-like receipts:
   - report share
   - report view
   - report revoke
   - admin action request
   - waiver submit
   - approval submit
   - release readback capture
2. Persist or expose event outbox rows in the local A3 store and SQLite adapter.
3. Add idempotency and conflict behavior to the same write paths.
4. Add fail-closed RBAC tests around write paths using the existing
   Auth/RBAC boundary.
5. Add A1/A2 schema drift tests against `docs/a1/schemas` and `docs/a2/schemas`.
6. Add bundle reseal impact fields when source artifacts, generated artifacts,
   waiver/approval records, thresholds, or judge/policy versions change.
7. Only after the contract spine is stronger, do a focused dashboard visual
   polish pass.

## Efficient Validation Ladder

For docs-only or index-only changes:

```text
git diff --check
```

For A3 service contract changes:

```text
node --test tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_tenant_event_source_artifact_contract.test.mjs
python scripts/cl_guard.py commercial
python scripts/cl_guard.py hygiene
git diff --check
```

For dashboard or UI workflow changes:

```text
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/a3_api_server.test.mjs
npm.cmd run test:e2e
python scripts/cl_guard.py commercial
python scripts/cl_guard.py hygiene
git diff --check
```

For final PR confidence:

```text
node --test tests/a3/*.mjs
npm.cmd run test:e2e
python scripts/cl_guard.py commercial
python scripts/cl_guard.py hygiene
git diff --check
```

## Beginner Explanation

A3 has already built the product console shape. The main missing part is not
"more pages"; it is the SaaS backbone:

- who did the action
- whether they had permission
- whether the same request was already submitted
- what audit event was recorded
- what usage meter changed
- whether the evidence bundle must be resealed

That is the clean path from student MVP toward commercial Ashr-style SaaS.
