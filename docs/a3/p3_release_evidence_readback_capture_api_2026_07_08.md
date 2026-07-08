# P3 Release Evidence Readback Capture API - 2026-07-08

## Goal

This round moves A3 release evidence readback from static redacted fixtures toward an API-backed and DB-backed SaaS control plane.

The new capability lets an external CI worker, GitHub App worker, or future A1 platform service submit a sanitized readback receipt back into A3 after it checks whether GitHub really contains the expected check run, PR comment, or required-check configuration.

## Lane declaration

- Lane: A3 Product / Workflow / Commercial UI.
- Language/framework: Node.js ESM, local HTTP API, SQLite-backed store contract.
- Service boundary: `services/report`.
- API contract added:
  - `POST /api/a3/releases/:releaseId/readbacks`
  - `GET /api/a3/releases/:releaseId/readbacks`
- DB contract extended:
  - `release_evidence_readbacks`
  - release-scoped readback index
- Event/audit contract added:
  - `release_evidence.readback_captured`
- Artifact contract extended:
  - `release_evidence_readback`
- Usage meter extended:
  - `release_evidence_readbacks`

## What changed

1. A3 can accept a sanitized readback receipt through an API route.
2. A3 stores the receipt in the memory store and SQLite-backed store.
3. A3 returns a capture receipt with a payload hash and audit event id.
4. A3 supports idempotency keys for readback capture.
5. A3 keeps readback idempotency separate from A1/A2 import receipts.
6. A3 redacts nested `authorization`, token, email, cookie, password, key, and secret-like values.
7. A3 exposes `GET /readbacks` for release-scoped readback inspection.
8. A3 v2 release evidence summary uses the latest captured readback to override static fixture state.
9. A3 SQLite persistence writes current authority readback rows without duplicating overridden static rows.
10. A3 usage ledger counts captured release evidence readbacks as a commercial meter.
11. A3 artifact registry treats captured readbacks as control-plane evidence.
12. A3 tests verify cross-tenant readback access returns 404.
13. A3 tests verify readback capture does not expose raw bearer headers or actor emails.
14. A3 tests verify stale PR comment readback can drive `body_hash_match=false`.
15. A3 tests verify persisted readbacks survive SQLite store reload.

## Expected request shape

The API accepts a sanitized receipt-like object. It must not contain raw tokens, raw response bodies, cookies, or private account values.

```json
{
  "readback": {
    "schema_version": "a3.github_check_readback_receipt.v1",
    "provider": "github",
    "resource_kind": "github_check",
    "readback_id": "ghcrb_redacted_confirmed",
    "readback_status": "readback_confirmed",
    "payload_hash": "sha256_redacted_payload",
    "expected": {},
    "observed": {},
    "matches": {}
  },
  "actor_hash": "actor_[REDACTED_HASH]"
}
```

## Current safety boundary

- This round did not call live Ashr API.
- This round did not call live GitHub API.
- This round did not read `.env.local`.
- This round did not publish or mutate branch protection.
- This round did not store raw token, cookie, email, account id, Authorization header, or private response body.
- Captured readback means "A3 accepted sanitized evidence." It does not automatically mean GitHub branch protection is enforced.

## A1/A2 calibration

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 scenario, judge, score, pass/fail, failure taxonomy, and policy semantics were not changed.
- A3 consumes A1/A2 evidence downstream and adds product workflow proof around release review and GitHub/CI handoff.
- A3 readback confirmed is not the same thing as A1 release evidence verifier passed.
- Future A3 adapter work should import A1 verifier packets rather than modifying A1 core logic.

## SaaS value

This closes one important gap in the commercial SaaS direction:

```text
static fixture -> API-backed receipt capture
mock readback -> persisted DB authority row
local report -> audit-linked release evidence
generated artifact -> externally read-back control state
```

## Growth points

1. Add live GitHub App worker that calls GitHub read APIs and submits sanitized readback receipts.
2. Add maintainer-approved branch-protection readback for required-check enforcement.
3. Add A1 release evidence verifier adapter instead of treating GitHub readback as full release verification.
4. Add Postgres persistence for readback receipts with RLS tenant isolation.
5. Add OpenAPI schema for the readback capture routes.
6. Add RBAC policy: only release owner, reviewer, CI service account, or auditor can submit readbacks.
7. Add signed service-account authentication for CI readback submission.
8. Add replay protection beyond idempotency, such as nonce and timestamp windows.
9. Add immutable append-only readback history table separate from current authority rows.
10. Add readback diff API for stale-to-confirmed and confirmed-to-stale transitions.
11. Add dashboard UI panel for readback history and latest authority state.
12. Add hosted report section for readback capture evidence.
13. Add audit bundle reseal trigger when readback state changes.
14. Add artifact bundle manifest entries for each captured readback.
15. Add Slack/Teams notification when readback becomes stale or missing.
16. Add usage quota guardrail for repeated readback checks.
17. Add customer-facing trust report summary for release evidence controls.
18. Add failure taxonomy for readback failures: permission denied, missing, stale, deleted, API unavailable.
19. Add Playwright E2E coverage for the dashboard readback UI once it exists.
20. Add CI job that uploads sanitized readback evidence after `a3_gate_cli` generates PR artifacts.

## Verification used

```text
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/artifact_registry.test.mjs
```

Result at document time: 21 pass, 0 fail.
