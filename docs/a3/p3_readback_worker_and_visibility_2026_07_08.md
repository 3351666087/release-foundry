# A3 P3 Readback Worker And Visibility

Date: 2026-07-08

## Purpose

This round continues the A3 commercial SaaS path from `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

A3 already had release evidence readback capture APIs. This round makes that path usable by a CI/worker-style caller and visible in the customer-facing A3 surfaces.

## What Changed

- Added a safe readback capture CLI:
  - `services/report/a3_readback_capture_cli.mjs`
  - dry-run by default
  - `--submit` posts sanitized readback evidence to `/api/a3/releases/:releaseId/readbacks`
  - supports `--output-receipt` for CI artifacts
- Added tests:
  - `tests/a3/a3_readback_capture_cli.test.mjs`
- Added A1/A2 contract alignment artifact:
  - `docs/a3/p3_readback_a1_a2_contract_alignment_2026_07_08.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_readback_worker_round_2026_07_08.md`
- Exposed readback history in API-backed dashboard payload:
  - `release_evidence_readbacks`
  - `release_evidence_summary.readback_records`
  - `readback_status_counts`
  - `readback_resource_counts`
- Exposed readback history in report exports:
  - JSON `release_evidence_summary`
  - Markdown `## Release Evidence Summary`
  - dashboard Release Evidence panel
  - Report Center tile text
  - print/PDF-ready report section

## A1/A2 Boundary

Readback means "the external release-control surface was checked again after publication."

It does not mean:

- A1 runner passed.
- A1 trace/tool-call evidence is valid.
- A2 judge passed.
- A2 failure taxonomy is correct.

A3 keeps readback evidence downstream of A1/A2:

- A1 remains the source of RunResult, trace, observation, and tool-call evidence.
- A2 remains the source of GradeResult, score, pass/fail, judge result, rubric result, and failure class evidence.
- A3 uses readback only to prove release/report/GitHub control-plane state.

## Safety

- No `.env.local` was read.
- No ReleaseFoundry API call was made.
- No live GitHub API call was made.
- No branch-protection mutation was made.
- No token, cookie, email, Authorization header, raw key, account data, or secret value was committed.
- CLI and store redaction remove nested secret-like fields before receipts are written or submitted.

## Verification

Focused verification:

```text
node --check services/report/a3_readback_capture_cli.mjs
node --test tests/a3/a3_readback_capture_cli.test.mjs
node --test tests/a3/a3_readback_capture_cli.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
git diff --check
```

Result:

```text
81 tests
81 pass
0 fail
```

## Remaining Work

1. Add a maintainer-approved CI or GitHub App worker that performs live readback and calls the A3 readback API.
2. Add real hosted auth/RBAC before readback evidence can affect a production release decision.
3. Move the current SQLite/local contract toward production Postgres/RLS and object-storage-backed audit bundles.
