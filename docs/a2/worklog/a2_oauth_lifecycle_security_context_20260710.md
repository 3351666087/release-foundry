# A2 OAuth Lifecycle Security Context - 2026-07-10

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Service boundary: `services/judge/evidence_readiness.py`.
- Contract: `docs/a2/schemas/evidence_readiness.schema.json`.
- Generated artifact: `fixtures/a2/results/a2_evidence_readiness_report.json`.

## Upstream Signal

- `origin/main` remains at `5dbf4ee Merge pull request #30 from 3351666087/agent/main-sync-a1-a2-a3-readme-20260710`.
- `origin/agent/a1-local-sdk-runner` advanced to `9b39a85 Fix OAuth evidence and generated route fixture`.
- The A1 branch adds public GitHub account connection evidence, OAuth security review notes, and `services/api/migrations/006_a1_oauth_lifecycle.sql`.

## A2 Behavior

- A2 now has a forward-compatible `a1_oauth_lifecycle_security` evidence readiness block.
- When the SQL or public evidence file is absent from the current branch, A2 emits a stable missing summary.
- When present, A2 verifies OAuth lifecycle tables, digest-only fields, recursive public metadata checks, forbidden OAuth secret keys, reference-only token storage, state/code replay controls, account takeover controls, session fixation controls, revocation, audit/outbox, hard-delete rejection, append-only audit records, tenant RLS, public evidence redaction, replay denial, scope boundary, and provider-token revocation before local deletion.
- `c3_grading_ready` remains false; this is auth policy context, not reviewed ReleaseFoundry grading evidence.

## Verification Plan

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- A3 compatibility contract because public evidence readiness output changed.
- `git diff --check`
- staged secret scan before commit.

## Notes

- No live ReleaseFoundry API call was needed for this change.
- No OAuth provider API was called in this A2 run.
- No private evidence path was read or committed.
