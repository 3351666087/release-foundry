# A2 China Payment SQL Context - 2026-07-10

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Service boundary: `services/judge/evidence_readiness.py`.
- Contract: `docs/a2/schemas/evidence_readiness.schema.json`.
- Generated artifact: `fixtures/a2/results/a2_evidence_readiness_report.json`.

## Upstream Signal

- `origin/main` remains at `5dbf4ee Merge pull request #30 from 3351666087/agent/main-sync-a1-a2-a3-readme-20260710`.
- `origin/agent/a1-local-sdk-runner` advanced to `9393a8f Build China-first payment runtime and fail-closed ingestion`.
- The A1 branch adds `docs/a1/schemas/a1_china_payment_migration_manifest.json` with China-first payment SQL persistence for WeChat Pay, Alipay, and domestic bank-card references.

## A2 Behavior

- A2 now has a forward-compatible `a1_china_payment_migration` evidence readiness block.
- When the A1 manifest is absent from the current branch, A2 emits a public-safe missing summary instead of dropping the contract field.
- When present, A2 verifies CNY provider coverage, tenant RLS coverage, mutable-audited and append-only table classes, idempotency keys, billing-ledger provider linkage, reference-only credential storage, hash-only notification evidence, object-reference bill files, hash-only mutation evidence, and no raw card or provider payload persistence.
- `c3_grading_ready` remains false; this contract is payment SQL policy context, not reviewed ReleaseFoundry grading evidence.

## Verification Plan

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- A3 compatibility contract if public evidence output changes.
- `git diff --check`
- staged secret scan before commit.

## Notes

- No live ReleaseFoundry API call was needed for this change.
- No payment provider API was called.
- No private evidence path was read or committed.
