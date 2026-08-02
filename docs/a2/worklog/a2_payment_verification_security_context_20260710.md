# A2 Payment Verification Security Context - 2026-07-10

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Service boundary: `services/judge/evidence_readiness.py`.
- Contract: `docs/a2/schemas/evidence_readiness.schema.json`.
- Generated artifact: `fixtures/a2/results/a2_evidence_readiness_report.json`.

## Upstream Signal

- `origin/main` remains at `5dbf4ee Merge pull request #30 from 3351666087/agent/main-sync-a1-a2-a3-readme-20260710`.
- `origin/agent/a1-local-sdk-runner` advanced to `a559189 Harden public account readiness receipts`.
- The A1 branch adds public payment/account hardening docs and `services/api/migrations/005_a1_payment_verification_security.sql`.

## A2 Behavior

- A2 now has a forward-compatible `a1_payment_verification_security` evidence readiness block.
- When the SQL file is absent from the current branch, A2 emits a stable missing summary.
- When present, A2 verifies recursive public metadata checks, forbidden card/payment/secret aliases, verification artifact digest fields, freshness windows, append-only artifact semantics, verified notification requirements, fail-closed status transitions, trusted apply functions, project-scoped RLS, no-bypass-RLS assertions, and metadata-safe constraints.
- `c3_grading_ready` remains false; this is payment verification policy context, not reviewed ReleaseFoundry grading evidence.

## Verification Plan

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- A3 compatibility contract because public evidence readiness output changed.
- `git diff --check`
- staged secret scan before commit.

## Notes

- No live ReleaseFoundry API call was needed for this change.
- No payment provider API was called.
- No private evidence path was read or committed.
