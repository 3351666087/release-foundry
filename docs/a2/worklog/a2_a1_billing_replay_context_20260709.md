# A2 A1 Billing Replay Evidence Context - 2026-07-09

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Service boundary: `services/judge/evidence_readiness.py`.
- Contract: `docs/a2/schemas/evidence_readiness.schema.json`.
- Generated artifact: `fixtures/a2/results/a2_evidence_readiness_report.json`.

## Upstream Signal

- `origin/agent/a1-local-sdk-runner` exposes `docs/a1/evidence/billing_replay_fixture_round35.json`.
- `origin/main` does not yet carry that billing replay fixture in this local fetch.
- A2 now treats the fixture as optional public-safe billing usage context when it appears on the active branch.

## A2 Behavior

- Summarizes ledger event count, provider event count, usage units, currency totals, billing snapshot hash presence, accepted/duplicate ingest status, and duplicate idempotency.
- Recursively rejects raw payload, secret value, and raw secret flags.
- Marks the context ready only when the fixture is public-safe, has billing/provider events, and proves duplicate webhook idempotency.
- Keeps `c3_grading_ready=false`; billing replay evidence cannot satisfy reviewed ReleaseFoundry grading rows.

## Verification Plan

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- `git diff --check`
- staged secret scan before commit.

## Notes

- No live ReleaseFoundry API call was needed for this change.
- No private evidence path was read or committed.
